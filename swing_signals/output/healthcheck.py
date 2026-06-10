"""healthchecks.io dead-man's-switch ping (file 12 §10).

The scheduled run pings a check URL on completion, or its ``/fail`` endpoint on
failure, so a *missed* run — scheduler outage, a crash before alerting, the repo
being auto-disabled — is surfaced by healthchecks.io independently of this app.
That covers the single most dangerous failure mode of a hands-off system: silent
non-execution. A no-op when ``SWING_HEALTHCHECK_URL`` is unset, so callers can
ping unconditionally.
"""

from __future__ import annotations

import logging

log = logging.getLogger("swing_signals")


def ping(url: str | None, *, fail: bool = False, timeout: float = 10.0) -> None:
    """Ping the healthcheck URL (``/fail`` if ``fail``); never raises."""
    if not url:
        return
    target = url.rstrip("/") + "/fail" if fail else url
    try:
        import requests

        requests.get(target, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - monitoring must never break the run
        # Never log the URL: the check UUID in it is the only credential needed to
        # send fake "all good" pings, and these logs are public in CI.
        log.warning("healthcheck ping failed: %s", type(exc).__name__)
