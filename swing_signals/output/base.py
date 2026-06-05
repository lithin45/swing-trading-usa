"""The Alerter interface and a console backend used by --dry-run.

Concrete push backends (Telegram, email) implement ``Alerter`` in Stage 6. The
orchestrator can fan out to several; ``send_failure_alert`` runs on the exception
path so the user is told when a run *fails*, not only when it produces signals.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Alerter(Protocol):
    name: str

    def send(self, subject: str, body: str, meta: dict[str, Any] | None = None) -> None:
        """Deliver a normal daily-report message."""
        ...

    def send_failure_alert(self, error: str, meta: dict[str, Any] | None = None) -> None:
        """Deliver a failure notification (exception path)."""
        ...


class ConsoleAlerter:
    """Prints to stdout instead of sending. Used in --dry-run and tests."""

    name = "console"

    def send(self, subject: str, body: str, meta: dict[str, Any] | None = None) -> None:
        print(f"\n=== ALERT: {subject} ===\n{body}\n")

    def send_failure_alert(self, error: str, meta: dict[str, Any] | None = None) -> None:
        print(f"\n=== FAILURE ALERT ===\n{error}\n")
