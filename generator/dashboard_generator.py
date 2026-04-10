"""
Grafana Dashboard Generator
Generates a Grafana dashboard JSON for each service's SLOs.
Panels: error budget remaining, burn rate, SLI over time, event rate.
"""
import json
import logging
from pathlib import Path

from .models import ServiceSLO, SLODefinition

logger = logging.getLogger(__name__)
OUTPUT_DIR = Path(__file__).parent.parent / "dashboards" / "grafana"


def generate_dashboard(service_slo: ServiceSLO) -> dict:
    """Generate a complete Grafana dashboard for a service."""
    panels = []
    panel_id = 1
    y_pos    = 0

    # ── Row per SLO ──────────────────────────────────────────────────────────
    for slo in service_slo.slos:
        if slo.metric is None:
            continue

        svc    = service_slo.service_id
        slo_id = slo.slo_id

        # Row separator
        panels.append(_row_panel(panel_id, slo.name, y_pos))
        panel_id += 1
        y_pos    += 1

        # Stat: current SLI
        panels.append(_stat_panel(
            panel_id, "Current SLI (30d)",
            f"slo:sli_{svc}_{slo_id}:ratio_rate30d",
            slo.target, y_pos, x=0, w=4, h=4,
        ))
        panel_id += 1

        # Gauge: error budget remaining
        panels.append(_budget_gauge(
            panel_id,
            f"slo:error_budget_remaining_{svc}_{slo_id}",
            y_pos, x=4, w=4, h=4,
        ))
        panel_id += 1

        # Stat: budget consumed %
        panels.append(_stat_panel(
            panel_id, "Budget Consumed",
            f"slo:error_budget_consumed_{svc}_{slo_id}",
            None, y_pos, x=8, w=4, h=4, unit="percentunit",
            color_mode="thresholds",
            thresholds=[0, 0.5, 0.9],
            threshold_colors=["green", "yellow", "red"],
        ))
        panel_id += 1

        # Stat: burn rate ratio
        panels.append(_stat_panel(
            panel_id, "Burn Rate (1h vs 5m)",
            (f"(\n  slo:sli_{svc}_{slo_id}:ratio_rate5m\n)"
             f"\n/\n(\n  {slo.target}\n)"),
            None, y_pos, x=12, w=4, h=4, unit="short",
        ))
        panel_id += 1

        y_pos += 4

        # Timeseries: SLI over time
        panels.append(_timeseries_panel(
            panel_id, f"SLI — {slo.name}",
            [
                (f"slo:sli_{svc}_{slo_id}:ratio_rate5m",   "5m SLI"),
                (f"slo:sli_{svc}_{slo_id}:ratio_rate1h",   "1h SLI"),
                (f"slo:sli_{svc}_{slo_id}:ratio_rate30d",  "30d SLI"),
                (f"vector({slo.target})",                   f"Target ({slo.target_pct})"),
            ],
            y_pos, x=0, w=12, h=8, unit="percentunit",
        ))
        panel_id += 1

        # Timeseries: error budget remaining over time
        panels.append(_timeseries_panel(
            panel_id, f"Error Budget Remaining — {slo.name}",
            [
                (f"slo:error_budget_remaining_{svc}_{slo_id}", "Budget remaining"),
                (f"vector(0.1)", "Warning threshold (10%)"),
                (f"vector(0)",   "Exhausted"),
            ],
            y_pos, x=12, w=12, h=8, unit="percentunit",
        ))
        panel_id += 1

        y_pos += 8

    return {
        "id":           None,
        "uid":          f"slo-{service_slo.service}",
        "title":        f"SLO Dashboard — {service_slo.service}",
        "description":  f"SLO error budgets and burn rates for {service_slo.service}",
        "tags":         ["slo", "error-budget", service_slo.service, service_slo.team],
        "schemaVersion": 38,
        "version":      1,
        "refresh":      "1m",
        "time":         {"from": "now-30d", "to": "now"},
        "timepicker":   {},
        "timezone":     "browser",
        "panels":       panels,
        "templating": {
            "list": [
                {
                    "name":       "datasource",
                    "type":       "datasource",
                    "pluginId":   "prometheus",
                    "current":    {"text": "Prometheus", "value": "prometheus"},
                    "hide":       0,
                }
            ]
        },
        "annotations": {"list": []},
        "links": [],
    }


def _row_panel(pid: int, title: str, y: int) -> dict:
    return {"id": pid, "type": "row", "title": title.upper(),
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "collapsed": False}


def _stat_panel(pid: int, title: str, expr: str, target: float | None,
                y: int, x: int = 0, w: int = 4, h: int = 4,
                unit: str = "percentunit", color_mode: str = "background",
                thresholds: list | None = None,
                threshold_colors: list | None = None) -> dict:
    th = thresholds or ([0, target * 0.95 if target else 0.9, target or 0.99])
    tc = threshold_colors or ["red", "yellow", "green"]
    return {
        "id": pid, "type": "stat", "title": title,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "datasource": {"type": "prometheus", "uid": "$datasource"},
        "targets": [{"expr": expr, "legendFormat": title, "refId": "A", "instant": True}],
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "decimals": 3,
                "color": {"mode": "thresholds"},
                "thresholds": {
                    "mode": "absolute",
                    "steps": [{"color": c, "value": None if i == 0 else th[i]}
                              for i, c in enumerate(tc)],
                },
            }
        },
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]},
                    "orientation": "auto", "textMode": "auto",
                    "colorMode": color_mode},
    }


def _budget_gauge(pid: int, expr: str, y: int, x: int = 4, w: int = 4, h: int = 4) -> dict:
    return {
        "id": pid, "type": "gauge", "title": "Error Budget Remaining",
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "datasource": {"type": "prometheus", "uid": "$datasource"},
        "targets": [{"expr": f"clamp_min({expr}, 0)", "legendFormat": "Budget", "refId": "A", "instant": True}],
        "fieldConfig": {
            "defaults": {
                "unit": "percentunit", "min": 0, "max": 1, "decimals": 3,
                "color": {"mode": "thresholds"},
                "thresholds": {
                    "mode": "percentage",
                    "steps": [
                        {"color": "red", "value": None},
                        {"color": "yellow", "value": 10},
                        {"color": "green", "value": 25},
                    ],
                },
            }
        },
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]},
                    "showThresholdLabels": False, "showThresholdMarkers": True},
    }


def _timeseries_panel(pid: int, title: str, targets: list[tuple[str, str]],
                      y: int, x: int = 0, w: int = 12, h: int = 8,
                      unit: str = "percentunit") -> dict:
    return {
        "id": pid, "type": "timeseries", "title": title,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "datasource": {"type": "prometheus", "uid": "$datasource"},
        "targets": [
            {"expr": expr, "legendFormat": legend, "refId": chr(65 + i)}
            for i, (expr, legend) in enumerate(targets)
        ],
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "custom": {"lineWidth": 2, "fillOpacity": 5},
            }
        },
        "options": {"tooltip": {"mode": "multi"}, "legend": {"displayMode": "list"}},
    }


def write_dashboard(service_slo: ServiceSLO) -> Path:
    """Generate and write Grafana dashboard JSON for a service."""
    dashboard = generate_dashboard(service_slo)
    output_path = OUTPUT_DIR / f"{service_slo.service}-slo-dashboard.json"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(dashboard, f, indent=2)

    logger.info("Written: %s (%d panels)", output_path.name, len(dashboard["panels"]))
    return output_path
