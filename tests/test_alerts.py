"""Alerting: channel build from secrets, fan-out isolation, chunking, payloads."""

from __future__ import annotations

from swing_signals.config_loader import Secrets, load_settings
from swing_signals.output.dispatch import build_alerters, dispatch, dispatch_failure
from swing_signals.output.email_smtp import build_message
from swing_signals.output.telegram import TelegramAlerter, chunk_text


class _Fake:
    def __init__(self, name: str, fail: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.sent: list[tuple[str, str]] = []
        self.failures: list[str] = []

    def send(self, subject, body, meta=None):
        if self.fail:
            raise RuntimeError("boom")
        self.sent.append((subject, body))

    def send_failure_alert(self, error, meta=None):
        if self.fail:
            raise RuntimeError("boom")
        self.failures.append(error)


# ── chunking ────────────────────────────────────────────────────────────────

def test_chunk_text_short_is_single():
    assert chunk_text("hello", 4096) == ["hello"]


def test_chunk_text_splits_under_limit_and_reconstructs():
    text = "\n".join(f"line {i} " + "x" * 60 for i in range(300))  # well over 4096
    chunks = chunk_text(text, 4096)
    assert len(chunks) > 1
    assert all(len(c) <= 4096 for c in chunks)
    assert "\n".join(chunks) == text  # line-boundary split reconstructs exactly


# ── fan-out ─────────────────────────────────────────────────────────────────

def test_dispatch_counts_and_isolates_a_failing_channel():
    ok1, bad, ok2 = _Fake("a"), _Fake("b", fail=True), _Fake("c")
    sent = dispatch([ok1, bad, ok2], "subj", "body")
    assert sent == 2  # the broken channel doesn't silence the others
    assert ok1.sent and ok2.sent


def test_dispatch_failure_isolation():
    ok, bad = _Fake("a"), _Fake("b", fail=True)
    assert dispatch_failure([ok, bad], "kaboom") == 1
    assert ok.failures == ["kaboom"]


# ── channel construction ─────────────────────────────────────────────────────

def test_build_alerters_empty_without_secrets():
    settings = load_settings()
    secrets = Secrets(_env_file=None)  # no creds anywhere
    assert build_alerters(settings, secrets) == []


def test_build_alerters_telegram_when_configured():
    settings = load_settings()
    secrets = Secrets(_env_file=None, telegram_bot_token="tok", telegram_chat_id="123")
    alerters = build_alerters(settings, secrets)
    assert any(a.name == "telegram" for a in alerters)


def test_build_alerters_email_when_configured():
    settings = load_settings()
    secrets = Secrets(
        _env_file=None, smtp_host="smtp.example.com",
        smtp_from="from@example.com", smtp_to="to@example.com",
    )
    assert any(a.name == "email" for a in build_alerters(settings, secrets))


# ── payloads ─────────────────────────────────────────────────────────────────

def test_email_message_construction():
    msg = build_message("from@x.com", "to@y.com", "Subj", "Body line")
    assert msg["From"] == "from@x.com"
    assert msg["To"] == "to@y.com"
    assert msg["Subject"] == "Subj"
    assert "Body line" in msg.get_content()


def test_telegram_send_posts_expected_payload(monkeypatch):
    posts: list[dict] = []

    class _Resp:
        status_code = 200
        text = "ok"

    def fake_post(url, json, timeout):
        posts.append(json)
        return _Resp()

    monkeypatch.setattr("requests.post", fake_post)
    TelegramAlerter("tok", "chat").send("Subj", "Body")
    assert posts and posts[0]["chat_id"] == "chat"
    assert "Subj" in posts[0]["text"] and "Body" in posts[0]["text"]
