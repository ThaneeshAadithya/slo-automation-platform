"""
SLO Weekly Report Generator.
Queries Prometheus, builds HTML + text reports, sends via email and Slack.

Usage:
    python -m reporter.generate
    python -m reporter.generate --dry-run
    python -m reporter.generate --output-html report.html
"""
import argparse
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from generator.loader import load_all_slos
from generator.models import ServiceSLO, SLODefinition
from .prometheus_client import PrometheusClient

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass
class SLOStatus:
    service:          str
    slo_name:         str
    team:             str
    target:           float
    current_sli:      Optional[float]
    budget_remaining: Optional[float]
    budget_consumed:  Optional[float]
    at_risk:          bool = False
    breached:         bool = False
    trend:            str  = "stable"  # improving | degrading | stable

    @property
    def status_label(self) -> str:
        if self.breached:       return "BREACHED"
        if self.at_risk:        return "AT RISK"
        return "HEALTHY"

    @property
    def status_color(self) -> str:
        if self.breached: return "#E74C3C"
        if self.at_risk:  return "#E67E22"
        return "#27AE60"

    @property
    def budget_pct(self) -> str:
        if self.budget_remaining is None:
            return "N/A"
        return f"{self.budget_remaining * 100:.1f}%"

    @property
    def sli_pct(self) -> str:
        if self.current_sli is None:
            return "N/A"
        return f"{self.current_sli * 100:.4f}%"


@dataclass
class WeeklyReport:
    generated_at:   datetime
    period:         str
    slo_statuses:   list[SLOStatus] = field(default_factory=list)
    total_slos:     int = 0
    healthy:        int = 0
    at_risk:        int = 0
    breached:       int = 0

    def compute_summary(self):
        self.total_slos = len(self.slo_statuses)
        self.healthy    = sum(1 for s in self.slo_statuses if s.status_label == "HEALTHY")
        self.at_risk    = sum(1 for s in self.slo_statuses if s.status_label == "AT RISK")
        self.breached   = sum(1 for s in self.slo_statuses if s.status_label == "BREACHED")

    @property
    def health_score(self) -> str:
        if self.total_slos == 0:
            return "N/A"
        score = self.healthy / self.total_slos * 100
        return f"{score:.0f}%"


def collect_slo_statuses(client: PrometheusClient, dry_run: bool) -> list[SLOStatus]:
    """Query Prometheus for all SLO metrics."""
    statuses = []

    for service_slo in load_all_slos():
        for slo in service_slo.slos:
            if slo.metric is None:
                continue

            svc    = service_slo.service_id
            slo_id = slo.slo_id

            if dry_run:
                # Return synthetic data for dry-run testing
                import random
                budget  = random.uniform(0.05, 0.95)
                current = slo.target - random.uniform(-0.005, 0.005)
                consumed = 1 - budget
            else:
                current  = client.get_sli(svc, slo_id)
                budget   = client.get_error_budget_remaining(svc, slo_id)
                consumed = client.get_error_budget_consumed(svc, slo_id)

            at_risk  = budget is not None and budget < slo.alerting.budget_low_threshold
            breached = (current is not None and current < slo.target) or \
                       (budget  is not None and budget < 0)

            statuses.append(SLOStatus(
                service=service_slo.service,
                slo_name=slo.name,
                team=service_slo.team,
                target=slo.target,
                current_sli=current,
                budget_remaining=budget,
                budget_consumed=consumed,
                at_risk=at_risk,
                breached=breached,
            ))

    return statuses


def render_html_report(report: WeeklyReport) -> str:
    """Render the HTML email report using Jinja2 template."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("weekly-report.html.j2")
    return template.render(report=report)


def render_text_report(report: WeeklyReport) -> str:
    """Render plain-text report for Slack/terminal."""
    lines = [
        f"📊 SLO Weekly Report — {report.period}",
        f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"Overall Health Score: {report.health_score}",
        f"  ✅ Healthy : {report.healthy}",
        f"  ⚠️  At Risk : {report.at_risk}",
        f"  🚨 Breached: {report.breached}",
        "",
        "─" * 60,
    ]

    # Group by team
    by_team: dict[str, list[SLOStatus]] = {}
    for s in sorted(report.slo_statuses, key=lambda x: (x.breached, x.at_risk), reverse=True):
        by_team.setdefault(s.team, []).append(s)

    for team, statuses in sorted(by_team.items()):
        lines.append(f"\n{team.upper()}")
        for s in statuses:
            icon = "🚨" if s.breached else "⚠️ " if s.at_risk else "✅"
            lines.append(
                f"  {icon} {s.service}/{s.slo_name:<30} "
                f"SLI={s.sli_pct:<12} Budget={s.budget_pct}"
            )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate SLO weekly report")
    parser.add_argument("--dry-run",     action="store_true", help="Use synthetic data")
    parser.add_argument("--output-html", help="Write HTML report to file")
    parser.add_argument("--output-text", help="Write text report to file")
    parser.add_argument("--no-email",    action="store_true", help="Skip email sending")
    parser.add_argument("--no-slack",    action="store_true", help="Skip Slack posting")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")

    client  = PrometheusClient()
    now     = datetime.utcnow()
    report  = WeeklyReport(
        generated_at=now,
        period=f"Week ending {now.strftime('%Y-%m-%d')}",
    )
    report.slo_statuses = collect_slo_statuses(client, dry_run=args.dry_run)
    report.compute_summary()

    html_report = render_html_report(report)
    text_report = render_text_report(report)

    # Print to terminal
    print(text_report)

    if args.output_html:
        Path(args.output_html).write_text(html_report)
        logger.info("HTML report written: %s", args.output_html)

    if args.output_text:
        Path(args.output_text).write_text(text_report)

    if not args.no_slack:
        from alerting.slack.notifier import post_slo_digest
        post_slo_digest(report, dry_run=args.dry_run)

    if not args.no_email and not args.dry_run:
        from reporter.email.sender import send_report
        send_report(html_report, text_report, report)


if __name__ == "__main__":
    main()
