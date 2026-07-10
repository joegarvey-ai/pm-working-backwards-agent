"""Retry-policy tests for the Dovetail research tool.

The retry wrapper must fast-fail on non-retryable 4xx responses (bad
request / expired auth / not found) and only retry transient failures
(429, 5xx, transport errors).
"""

from __future__ import annotations

import httpx
import pytest

from pm_agent_system.tools.dovetail_research import _dovetail_post_with_retry


@pytest.fixture(autouse=True)
def _no_backoff_sleep(monkeypatch):
    """Skip tenacity's real backoff so the retry tests run instantly."""
    import time as _time

    monkeypatch.setattr(_time, "sleep", lambda *_a, **_k: None)


def _make_poster(status_codes):
    """Return (fn, counter) where fn yields responses with the given statuses."""
    calls = {"n": 0}
    request = httpx.Request("POST", "https://dovetail.test/api/mcp")

    def _post(url, json=None, headers=None, timeout=None):
        i = min(calls["n"], len(status_codes) - 1)
        calls["n"] += 1
        return httpx.Response(status_codes[i], request=request, json={"ok": True})

    return _post, calls


def test_4xx_fast_fails_without_retry(monkeypatch):
    poster, calls = _make_poster([404])
    monkeypatch.setattr(httpx, "post", poster)

    with pytest.raises(httpx.HTTPStatusError):
        _dovetail_post_with_retry("u", {}, {}, 5)

    assert calls["n"] == 1  # no retries on a 404


def test_401_fast_fails_without_retry(monkeypatch):
    poster, calls = _make_poster([401])
    monkeypatch.setattr(httpx, "post", poster)

    with pytest.raises(httpx.HTTPStatusError):
        _dovetail_post_with_retry("u", {}, {}, 5)

    assert calls["n"] == 1


def test_5xx_is_retried_three_times(monkeypatch):
    poster, calls = _make_poster([503])
    monkeypatch.setattr(httpx, "post", poster)

    with pytest.raises(httpx.HTTPStatusError):
        _dovetail_post_with_retry("u", {}, {}, 5)

    assert calls["n"] == 3


def test_429_is_retried(monkeypatch):
    poster, calls = _make_poster([429])
    monkeypatch.setattr(httpx, "post", poster)

    with pytest.raises(httpx.HTTPStatusError):
        _dovetail_post_with_retry("u", {}, {}, 5)

    assert calls["n"] == 3


def test_transport_error_is_retried(monkeypatch):
    calls = {"n": 0}

    def _post(*_a, **_k):
        calls["n"] += 1
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "post", _post)

    with pytest.raises(httpx.ConnectError):
        _dovetail_post_with_retry("u", {}, {}, 5)

    assert calls["n"] == 3


def test_success_returns_response(monkeypatch):
    poster, calls = _make_poster([200])
    monkeypatch.setattr(httpx, "post", poster)

    resp = _dovetail_post_with_retry("u", {}, {}, 5)

    assert resp.status_code == 200
    assert calls["n"] == 1
