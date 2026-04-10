"""
HTML email sender for the SLO weekly report.
Uses SMTP with TLS. Supports AWS SES via SMTP relay.
"""
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reporter.generate import WeeklyReport

logger = logging.getLogger(__name__)

SMTP_HOST       = os.environ.get("SMTP_HOST", "email-smtp.us-east-1.amazonaws.com")
SMTP_PORT       = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER       = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD   = os.environ.get("SMTP_PASSWORD", "")
FROM_EMAIL      = os.environ.get("FROM_EMAIL", "slo-platform@example.com")
TO_EMAILS       = os.environ.get("TO_EMAILS", "engineering-leadership@example.com").split(",")


def send_report(html_body: str, text_body: str, report: "WeeklyReport") -> bool:
    """Send the SLO weekly report via email."""
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("SMTP credentials not set — skipping email send")
        return False

    subject = f"[SLO Report] {report.period} — Health: {report.health_score}"
    if report.breached > 0:
        subject = f"🚨 {subject} | {report.breached} BREACHED"
    elif report.at_risk > 0:
        subject = f"⚠️ {subject} | {report.at_risk} AT RISK"
    else:
        subject = f"✅ {subject}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = FROM_EMAIL
    msg["To"]      = ", ".join(TO_EMAILS)
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, TO_EMAILS, msg.as_string())
        logger.info("SLO report emailed to: %s", ", ".join(TO_EMAILS))
        return True
    except smtplib.SMTPException as e:
        logger.error("Failed to send email: %s", e)
        return False
