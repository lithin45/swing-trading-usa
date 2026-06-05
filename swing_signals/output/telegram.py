"""Telegram bot alerter (primary push channel, file 12 §5).

Outbound only — a bot token + chat id and an HTTPS ``sendMessage`` call; no server
or webhook needed to *send*. Messages are plain text (no Markdown parse mode) so
the report's em dashes / emoji / numbers never trip Telegram's entity parser, and
long reports are split into <=4096-char chunks (the API's per-message limit).
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("swing_signals.alerts")

_API = "https://api.telegram.org/bot{token}/sendMessage"
_MAX_CHARS = 4096


def chunk_text(text: str, limit: int = _MAX_CHARS) -> list[str]:
    """Split text into <=limit-char pieces, preferring line boundaries."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    cur = ""
    for line in text.split("\n"):
        while len(line) > limit:  # a single over-long line: hard-split it
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:limit])
            line = line[limit:]
        addition = line if not cur else "\n" + line
        if len(cur) + len(addition) > limit:
            chunks.append(cur)
            cur = line
        else:
            cur += addition
    if cur:
        chunks.append(cur)
    return chunks


class TelegramAlerter:
    name = "telegram"

    def __init__(self, token: str, chat_id: str, *, timeout: float = 20.0) -> None:
        self.token = token
        self.chat_id = chat_id
        self.timeout = timeout

    def _post(self, text: str) -> None:
        import requests

        url = _API.format(token=self.token)
        for chunk in chunk_text(text):
            resp = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": chunk, "disable_web_page_preview": True},
                timeout=self.timeout,
            )
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"telegram sendMessage HTTP {resp.status_code}: {resp.text[:200]}"
                )

    def send(self, subject: str, body: str, meta: dict[str, Any] | None = None) -> None:
        self._post(f"{subject}\n\n{body}")

    def send_failure_alert(self, error: str, meta: dict[str, Any] | None = None) -> None:
        self._post(f"⚠ swing-signals run FAILED\n\n{error}")
