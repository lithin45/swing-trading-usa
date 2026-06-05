"""healthcheck dead-man's-switch ping: no-op, success, /fail, error-swallowing."""

from __future__ import annotations

from swing_signals.output.healthcheck import ping


def test_ping_noop_on_empty(monkeypatch):
    called: list = []
    monkeypatch.setattr("requests.get", lambda *a, **k: called.append(a))
    ping(None)
    ping("")
    assert called == []  # nothing pinged when no URL configured


def test_ping_success_hits_url(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr("requests.get", lambda url, timeout: seen.update(url=url))
    ping("https://hc.example/abc")
    assert seen["url"] == "https://hc.example/abc"


def test_ping_failure_hits_fail_endpoint(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr("requests.get", lambda url, timeout: seen.update(url=url))
    ping("https://hc.example/abc/", fail=True)
    assert seen["url"] == "https://hc.example/abc/fail"


def test_ping_swallows_network_errors(monkeypatch):
    def boom(url, timeout):
        raise RuntimeError("network down")

    monkeypatch.setattr("requests.get", boom)
    ping("https://hc.example/abc")  # must not raise — monitoring never breaks the run
