"""
PagerDuty incident management for SLO breaches.
Auto-creates incidents when SLO is breached; resolves when recovered.
Integrates with PagerDuty Events API v2.
"""
import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)

PD_ROUTING_KEY   = os.environ.get("PAGERDUTY_ROUTING_KEY", "")
PD_EVENTS_URL    = "https://events.pagerduty.com/v2/enqueue"
PD_API_URL       = "https://api.pagerduty.com"
PD_API_TOKEN     = os.environ.get("PAGERDUTY_API_TOKEN", "")


@dataclass
class SLOBreach:
    service:          str
    slo_name:         str
    team:             str
    current_sli:      float
    target:           float
    burn_rate:        Optional[float]
    error_budget_remaining: float
    runbook_url:      str = ""


def _dedup_key(service: str, slo_name: str) -> str:
    """Stable deduplication key — same key resolves the same incident."""
    key = f"slo-breach-{service}-{slo_name}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def trigger_incident(breach: SLOBreach, dry_run: bool = False) -> Optional[str]:
    """
    Trigger a PagerDuty incident for an SLO breach.
    Returns the dedup key on success.
    """
    if not PD_ROUTING_KEY:
        logger.warning("PAGERDUTY_ROUTING_KEY not set — skipping incident creation")
        return None

    dedup_key = _dedup_key(breach.service, breach.slo_name)
    budget_pct = f"{breach.error_budget_remaining * 100:.1f}%"
    sli_pct    = f"{breach.current_sli * 100:.4f}%"
    target_pct = f"{breach.target * 100:.3f}%"

    payload = {
        "routing_key":  PD_ROUTING_KEY,
        "event_action": "trigger",
        "dedup_key":    dedup_key,
        "payload": {
            "summary": (
                f"SLO BREACH: {breach.service} {breach.slo_name} "
                f"| SLI={sli_pct} (target={target_pct})"
                f" | Budget={budget_pct} remaining"
            ),
            "severity":   "critical" if breach.error_budget_remaining < 0 else "warning",
            "source":     breach.service,
            "component":  breach.slo_name,
            "group":      breach.team,
            "class":      "slo-breach",
            "custom_details": {
                "service":         breach.service,
                "slo_name":        breach.slo_name,
                "team":            breach.team,
                "current_sli":     sli_pct,
                "target":          target_pct,
                "burn_rate":       str(breach.burn_rate) if breach.burn_rate else "unknown",
                "budget_remaining": budget_pct,
                "runbook_url":     breach.runbook_url,
            },
        },
        "links": [
            {"href": breach.runbook_url, "text": "Runbook"},
        ] if breach.runbook_url else [],
    }

    if dry_run:
        logger.info("[DRY RUN] Would trigger PagerDuty incident: %s/%s (key=%s)",
                    breach.service, breach.slo_name, dedup_key)
        return dedup_key

    try:
        resp = requests.post(PD_EVENTS_URL, json=payload, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        logger.info("PagerDuty incident triggered: %s (key=%s)",
                    result.get("message", ""), dedup_key)
        return dedup_key
    except requests.RequestException as e:
        logger.error("Failed to trigger PagerDuty incident: %s", e)
        return None


def resolve_incident(service: str, slo_name: str, dry_run: bool = False) -> bool:
    """Resolve an existing PagerDuty incident when SLO recovers."""
    if not PD_ROUTING_KEY:
        return False

    dedup_key = _dedup_key(service, slo_name)
    payload = {
        "routing_key":  PD_ROUTING_KEY,
        "event_action": "resolve",
        "dedup_key":    dedup_key,
        "payload": {
            "summary":  f"SLO Recovered: {service} {slo_name}",
            "severity": "info",
            "source":   service,
        },
    }

    if dry_run:
        logger.info("[DRY RUN] Would resolve PagerDuty incident: %s/%s (key=%s)",
                    service, slo_name, dedup_key)
        return True

    try:
        resp = requests.post(PD_EVENTS_URL, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("PagerDuty incident resolved: %s/%s", service, slo_name)
        return True
    except requests.RequestException as e:
        logger.error("Failed to resolve PagerDuty incident: %s", e)
        return False


def check_and_manage_incidents(statuses: list, dry_run: bool = False) -> dict:
    """
    Check all SLO statuses and trigger/resolve PagerDuty incidents as needed.
    Returns summary of actions taken.
    """
    triggered = []
    resolved  = []

    for status in statuses:
        if status.breached:
            breach = SLOBreach(
                service=status.service,
                slo_name=status.slo_name,
                team=status.team,
                current_sli=status.current_sli or 0.0,
                target=status.target,
                burn_rate=None,
                error_budget_remaining=status.budget_remaining or 0.0,
                runbook_url=f"https://runbooks.example.com/{status.service}/{status.slo_name}",
            )
            key = trigger_incident(breach, dry_run=dry_run)
            if key:
                triggered.append(f"{status.service}/{status.slo_name}")

        elif not status.at_risk and not status.breached:
            # Service is healthy — resolve any existing incident
            resolved_ok = resolve_incident(status.service, status.slo_name, dry_run=dry_run)
            if resolved_ok:
                resolved.append(f"{status.service}/{status.slo_name}")

    return {"triggered": triggered, "resolved": resolved}
