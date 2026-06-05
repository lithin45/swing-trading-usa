"""Email (SMTP) alerter — the redundant backup channel (file 12 §5).

Uses the stdlib ``smtplib`` + ``email.message`` (no extra dependency). STARTTLS by
default; works with any SMTP provider (Gmail app password, SES SMTP, etc.). The
point of the backup channel is that a single push channel failing never silences
a signal — the orchestrator fans out to Telegram *and* email.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

log = logging.getLogger("swing_signals.alerts")


def build_message(sender: str, recipient: str, subject: str, body: str) -> EmailMessage:
    """Construct the plaintext email (separated out so it's unit-testable)."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(body)
    return msg


class EmailAlerter:
    name = "email"

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str | None,
        password: str | None,
        sender: str,
        recipient: str,
        timeout: float = 20.0,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.sender = sender
        self.recipient = recipient
        self.timeout = timeout

    def _send(self, subject: str, body: str) -> None:
        msg = build_message(self.sender, self.recipient, subject, body)
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if self.user and self.password:
                smtp.login(self.user, self.password)
            smtp.send_message(msg)

    def send(self, subject: str, body: str, meta: dict[str, Any] | None = None) -> None:
        self._send(subject, body)

    def send_failure_alert(self, error: str, meta: dict[str, Any] | None = None) -> None:
        self._send("swing-signals run FAILED", error)
