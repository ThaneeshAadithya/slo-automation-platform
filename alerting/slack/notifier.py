"""
Slack SLO digest poster.
Posts weekly SLO status digest to a Slack channel.
"""
import json
import logging
import os
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from reporter.generate import WeeklyReport

logger = logging.getLogger(__name__)
SLACK_WEBHOOK = os.environ.get("SLACK_SLO_WEBHOOK_URL", "")
SLACK_CHANNEL = os.environ.get("SLACK_SLO_CHANNEL", "#slo-status")


def _status_emoji(status: str) -> str:
    return {"HEALTHY": ":white_check_mark:", "AT RISK": ":warning:", "BREACHED": ":rotating_light:"}.get(status, ":question:")


def post_slo_digest(report: "WeeklyReport", dry_run: bool = False) -> bool:
    if not SLACK_WEBHOOK:
        logger.info("SLACK_SLO_WEBHOOK_URL not set — skipping Slack digest")
        return False

    score_emoji = ":tada:" if report.breached == 0 else (":warning:" if report.at_risk > 0 else ":rotating_light:")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📊 SLO Weekly Digest — {report.period}"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Health Score*\n{score_emoji} {report.health_score}"},
                {"type": "mrkdwn", "text": f"*Total SLOs*\n{report.total_slos}"},
                {"type": "mrkdwn", "text": f"*✅ Healthy*\n{report.healthy}"},
                {"type": "mrkdwn", "text": f"*⚠️ At Risk*\n{report.at_risk}"},
                {"type": "mrkdwn", "text": f"*🚨 Breached*\n{report.breached}"},
            ],
        },
        {"type": "divider"},
    ]

    # Breached SLOs
    if report.breached > 0:
        breached_text = "\n".join(
            f":rotating_light: *{s.service}* / {s.slo_name} "
            f"— SLI={s.sli_pct}, Budget={s.budget_pct}"
            for s in report.slo_statuses if s.breached
        )
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*🚨 Breached SLOs*\n{breached_text}"},
        })

    # At-risk SLOs
    if report.at_risk > 0:
        at_risk_text = "\n".join(
            f":warning: *{s.service}* / {s.slo_name} "
            f"— Budget={s.budget_pct} remaining"
            for s in report.slo_statuses if s.at_risk and not s.breached
        )
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*⚠️ At-Risk SLOs*\n{at_risk_text}"},
        })

    # Per-service summary
    by_service: dict[str, list] = {}
    for s in sorted(report.slo_statuses, key=lambda x: x.service):
        by_service.setdefault(s.service, []).append(s)

    service_lines = []
    for svc, statuses in by_service.items():
        icons = "".join(_status_emoji(s.status_label) for s in statuses)
        worst = "BREACHED" if any(s.breached for s in statuses) else \
                "AT RISK" if any(s.at_risk for s in statuses) else "HEALTHY"
        min_budget = min((s.budget_remaining for s in statuses if s.budget_remaining is not None), default=None)
        budget_str = f"{min_budget * 100:.0f}%" if min_budget is not None else "N/A"
        service_lines.append(f"{icons} *{svc}* — {worst} | min budget: {budget_str}")

    blocks.append({"type": "divider"})
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": "*Service Summary*\n" + "\n".join(service_lines)},
    })
    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": f"Posted by SLO Automation Platform | {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')}"}],
    })

    payload = {"blocks": blocks, "channel": SLACK_CHANNEL}

    if dry_run:
        logger.info("[DRY RUN] Would post Slack digest:\n%s", json.dumps(payload, indent=2)[:500])
        return True

    try:
        resp = requests.post(SLACK_WEBHOOK, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("Slack digest posted to %s", SLACK_CHANNEL)
        return True
    except requests.RequestException as e:
        logger.error("Failed to post Slack digest: %s", e)
        return False
