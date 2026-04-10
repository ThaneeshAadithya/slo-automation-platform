"""
Prometheus Rule Generator
Generates recording rules and multi-window burn rate alerts from SLO definitions.

Based on Google SRE Workbook Chapter 5:
https://sre.google/workbook/alerting-on-slos/
"""
import logging
from pathlib import Path

import yaml

from .models import ServiceSLO, SLODefinition

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "prometheus" / "generated"

# Multi-window burn rate configurations (Google SRE Workbook)
# Each tuple: (short_window, long_window, burn_rate_multiplier, severity, page_or_ticket)
BURN_RATE_WINDOWS = [
    # Fast burn: consumes 2% of 30d budget in 1 hour  (14.4x rate) → PAGE
    ("5m",  "1h",  14.4, "critical", "page"),
    # Slow burn: consumes 5% of 30d budget in 6 hours (6x rate) → PAGE
    ("30m", "6h",  6.0,  "critical", "page"),
    # Slow burn: consumes 10% in 24h (3x rate) → ticket
    ("2h",  "1d",  3.0,  "warning",  "ticket"),
    # Very slow: consumes 10% in 3 days (1x rate) → ticket
    ("6h",  "3d",  1.0,  "warning",  "ticket"),
]


def generate_service_rules(service_slo: ServiceSLO) -> dict:
    """Generate all Prometheus rules for a single service."""
    groups = []

    for slo in service_slo.slos:
        if slo.metric is None:
            logger.warning("SLO %s/%s has no metric config — skipping", service_slo.service, slo.name)
            continue

        # Recording rules group
        recording_group = _generate_recording_rules(service_slo, slo)
        groups.append(recording_group)

        # Alert rules group
        alert_group = _generate_alert_rules(service_slo, slo)
        groups.append(alert_group)

    return {
        "apiVersion": "monitoring.coreos.com/v1",
        "kind": "PrometheusRule",
        "metadata": {
            "name": f"slo-{service_slo.service}",
            "namespace": "monitoring",
            "labels": {
                "prometheus": "kube-prometheus",
                "role": "alert-rules",
                "slo-managed": "true",
                "team": service_slo.team,
                "service": service_slo.service,
            },
        },
        "spec": {"groups": groups},
    }


def _generate_recording_rules(service: ServiceSLO, slo: SLODefinition) -> dict:
    """Generate recording rules for fast queries in dashboards and alerts."""
    svc = service.service_id
    slo_id = slo.slo_id
    windows = ["5m", "30m", "1h", "2h", "6h", "1d", "3d", "30d"]

    rules = []
    for win in windows:
        # SLI ratio — fraction of good events
        rules.append({
            "record": f"slo:sli_{svc}_{slo_id}:ratio_rate{win}",
            "expr": _sli_ratio_expr(slo, win),
        })

    # Error budget remaining (30d window)
    rules.append({
        "record": f"slo:error_budget_remaining_{svc}_{slo_id}",
        "expr": (
            f"(slo:sli_{svc}_{slo_id}:ratio_rate30d - {slo.target})"
            f" / (1 - {slo.target})"
        ),
    })

    # Error budget consumed (for dashboard)
    rules.append({
        "record": f"slo:error_budget_consumed_{svc}_{slo_id}",
        "expr": (
            f"1 - clamp_min(slo:error_budget_remaining_{svc}_{slo_id}, 0)"
        ),
    })

    return {
        "name": f"slo.recordings.{svc}.{slo_id}",
        "interval": "30s",
        "rules": rules,
    }


def _generate_alert_rules(service: ServiceSLO, slo: SLODefinition) -> dict:
    """Generate multi-window burn rate alerts."""
    svc    = service.service_id
    slo_id = slo.slo_id
    rules  = []

    for short_win, long_win, burn_rate, severity, alert_type in BURN_RATE_WINDOWS:
        # Skip page alerts if service doesn't want paging
        if alert_type == "page" and not slo.alerting.page_on_burn:
            continue

        # Burn rate threshold = multiplier * error_rate
        threshold = burn_rate * slo.error_rate

        alert_name = (
            f"SLOBurnRate{svc.replace('_', '').title()}"
            f"{slo_id.replace('_', '').title()}"
            f"{'Fast' if burn_rate >= 6 else 'Slow'}{'Page' if alert_type == 'page' else 'Ticket'}"
        )

        rules.append({
            "alert": alert_name,
            "expr": (
                f"(\n"
                f"  slo:sli_{svc}_{slo_id}:ratio_rate{short_win} < (1 - {threshold:.6f})\n"
                f")\nand (\n"
                f"  slo:sli_{svc}_{slo_id}:ratio_rate{long_win}  < (1 - {threshold:.6f})\n"
                f")"
            ),
            "for": "2m" if alert_type == "page" else "15m",
            "labels": {
                "severity":   severity,
                "service":    service.service,
                "slo":        slo.name,
                "team":       service.team,
                "alert_type": alert_type,
                "burn_rate":  str(burn_rate),
            },
            "annotations": {
                "summary": (
                    f"SLO burn rate alert: {service.service} {slo.name}"
                ),
                "description": (
                    f"Service {service.service} is burning its {slo.name} error budget "
                    f"at {burn_rate}x the allowed rate.\n"
                    f"Short window ({short_win}) and long window ({long_win}) both below threshold.\n"
                    f"Current SLI: {{{{ $value | humanizePercentage }}}}"
                    f" (target: {slo.target_pct})"
                ),
                "burn_rate":   str(burn_rate),
                "window_short": short_win,
                "window_long":  long_win,
                "runbook_url":  slo.annotations.runbook_url or f"https://runbooks.example.com/{service.service}/{slo.name}",
            },
        })

    # Budget low alert — fires when remaining budget < threshold
    if slo.alerting.ticket_on_budget_low:
        threshold_pct = int(slo.alerting.budget_low_threshold * 100)
        rules.append({
            "alert": f"SLOErrorBudgetLow{svc.replace('_', '').title()}{slo_id.replace('_', '').title()}",
            "expr": (
                f"slo:error_budget_remaining_{svc}_{slo_id}"
                f" < {slo.alerting.budget_low_threshold}"
            ),
            "for": "5m",
            "labels": {
                "severity":   "warning",
                "service":    service.service,
                "slo":        slo.name,
                "team":       service.team,
                "alert_type": "budget",
            },
            "annotations": {
                "summary": f"Error budget below {threshold_pct}%: {service.service} {slo.name}",
                "description": (
                    f"Less than {threshold_pct}% of the 30-day error budget remains "
                    f"for {service.service} {slo.name}.\n"
                    f"Remaining: {{{{ $value | humanizePercentage }}}}"
                ),
                "runbook_url": slo.annotations.runbook_url or "",
            },
        })

    return {
        "name": f"slo.alerts.{svc}.{slo_id}",
        "rules": rules,
    }


def _sli_ratio_expr(slo: SLODefinition, window: str) -> str:
    """Build SLI ratio PromQL expression for a given window."""
    good  = slo.metric.good_query.replace("{{.window}}", window)
    total = slo.metric.total_query.replace("{{.window}}", window)
    return (
        f"(\n  {good.strip()}\n)\n"
        f"/\n(\n  {total.strip()}\n or vector(1))"
    )


def write_rules(service_slo: ServiceSLO) -> Path:
    """Generate and write Prometheus rules for a service."""
    rules = generate_service_rules(service_slo)
    output_path = OUTPUT_DIR / f"{service_slo.service}-slo-rules.yaml"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        yaml.dump(rules, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    logger.info("Written: %s (%d groups)", output_path.name, len(rules["spec"]["groups"]))
    return output_path
