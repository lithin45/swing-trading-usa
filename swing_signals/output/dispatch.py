"""Build the configured alert channels and fan a message out to all of them.

A channel is only built when (a) it's listed in ``alerts.channels`` and (b) its
secrets are present — so a missing token just disables that channel rather than
erroring. Delivery is best-effort per channel: one channel failing never stops the
others (file 12 §5, "a single channel failure never silences a signal"), and the
caller can fall back to the console if every channel is unavailable.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base import Alerter

if TYPE_CHECKING:
    from ..config_loader import Secrets, Settings

log = logging.getLogger("swing_signals.alerts")


def _reveal(secret) -> str | None:
    return secret.get_secret_value() if secret is not None else None


def build_alerters(settings: Settings, secrets: Secrets) -> list[Alerter]:
    """Instantiate the alert channels that are both configured and credentialed."""
    channels = settings.alerts.channels
    alerters: list[Alerter] = []

    if "telegram" in channels and secrets.telegram_bot_token and secrets.telegram_chat_id:
        from .telegram import TelegramAlerter
        token = _reveal(secrets.telegram_bot_token)
        if token:
            alerters.append(TelegramAlerter(token, secrets.telegram_chat_id))

    if "email" in channels and secrets.smtp_host and secrets.smtp_from and secrets.smtp_to:
        from .email_smtp import EmailAlerter
        alerters.append(EmailAlerter(
            host=secrets.smtp_host, port=secrets.smtp_port,
            user=secrets.smtp_user, password=_reveal(secrets.smtp_password),
            sender=secrets.smtp_from, recipient=secrets.smtp_to,
        ))

    return alerters


def _scrub(exc: Exception) -> str:
    """Exception text safe for (public CI) logs — Telegram embeds its token in URLs."""
    from ..data.retry import sanitize_url

    text = str(exc)
    if "/bot" in text:
        return f"{type(exc).__name__}: {sanitize_url(text.split(' for url', 1)[0])}"
    return text


def dispatch(alerters: list[Alerter], subject: str, body: str) -> int:
    """Send the report to every channel; return how many succeeded."""
    sent = 0
    for alerter in alerters:
        try:
            alerter.send(subject, body)
            sent += 1
        except Exception as exc:  # noqa: BLE001 - one channel failing must not stop others
            log.warning("alert via %s failed: %s", alerter.name, _scrub(exc))
    return sent


def dispatch_failure(alerters: list[Alerter], error: str) -> int:
    """Send a failure notification to every channel; return how many succeeded."""
    sent = 0
    for alerter in alerters:
        try:
            alerter.send_failure_alert(error)
            sent += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("failure-alert via %s failed: %s", alerter.name, _scrub(exc))
    return sent
