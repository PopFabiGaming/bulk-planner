"""Send email-notifikation med resume af ugens madplan."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

LOG = logging.getLogger("mailer")


def send_summary(to: str, subject: str, body_text: str, body_html: str,
                  host: str, port: int, user: str, password: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.set_content(body_text)
    msg.add_alternative(body_html, subtype="html")

    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)
    LOG.info("Mail sendt til %s", to)


def send_error(to: str, error_text: str, host: str, port: int,
                user: str, password: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = "Bulk-planner FEJLEDE — uge mangler"
    msg["From"] = user
    msg["To"] = to
    msg.set_content(
        "Den ugentlige madplan-pipeline fejlede:\n\n"
        f"{error_text}\n\n"
        "Tjek GitHub Actions-loggen for detaljer."
    )
    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)
