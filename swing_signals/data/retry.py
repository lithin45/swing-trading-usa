"""Retry/backoff for network calls + a transient/permanent error taxonomy.

Wrap any provider network call with ``@with_retry`` so transient failures
(timeouts, connection resets, HTTP 429/5xx) are retried with exponential
backoff, while permanent failures (bad symbol, 4xx) fail fast. This is what lets
the data layer handle rate limits gracefully.
"""

from __future__ import annotations

import logging

import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger("swing_signals.data")


class TransientDataError(Exception):
    """Retryable: rate limit, timeout, 5xx, transient network error."""


class PermanentDataError(Exception):
    """Not retryable: bad symbol, 4xx (other than 429), parse failure."""


_TRANSIENT = (
    TransientDataError,
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    ConnectionError,
    TimeoutError,
)


def with_retry(fn=None, *, attempts: int = 4, base: float = 1.0, cap: float = 20.0):
    """Decorator adding exponential-backoff retries to a network call.

    Usable bare (``@with_retry``) or parameterized (``@with_retry(attempts=5)``).
    Only :data:`_TRANSIENT` exceptions are retried; everything else propagates
    immediately. The original exception is re-raised after the final attempt.
    """
    decorator = retry(
        reraise=True,
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=base, max=cap),
        retry=retry_if_exception_type(_TRANSIENT),
        before_sleep=before_sleep_log(log, logging.WARNING),
    )
    return decorator if fn is None else decorator(fn)


def sanitize_url(url: str) -> str:
    """Strip the query string and any /bot<token>/ path segment from a URL.

    Several providers carry the API key in the query (?token=, ?apikey=) and
    Telegram carries it in the path; exception messages with the raw URL get
    retried/logged/printed, and on a public repo those logs are world-readable.
    GitHub masks exact secret values, but only there — keep the logs clean at
    the source instead of relying on platform redaction.
    """
    base = url.split("?", 1)[0]
    if "/bot" in base:  # api.telegram.org/bot<TOKEN>/method
        head, _, tail = base.partition("/bot")
        method = tail.split("/", 1)[1] if "/" in tail else ""
        base = f"{head}/bot***/{method}"
    return base


def classify_http(response: requests.Response) -> None:
    """Raise the right error type for a bad HTTP status (no-op on 2xx/3xx).

    429 and 5xx → transient (retry); other 4xx → permanent (fail fast).
    The URL is sanitized: query strings carry API keys for several providers.
    """
    code = response.status_code
    if code < 400:
        return
    if code == 429 or code >= 500:
        raise TransientDataError(f"HTTP {code} (transient) for {sanitize_url(response.url)}")
    raise PermanentDataError(f"HTTP {code} (permanent) for {sanitize_url(response.url)}")
