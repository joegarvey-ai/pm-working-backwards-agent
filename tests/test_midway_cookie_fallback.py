"""Integration test: midway cookie fallback when cookie file is missing.

Validates Requirements 5.5 and 11.5: when MIDWAY_COOKIE_PATH points at a
nonexistent file while a bearer token is set, the auth resolver logs a
warning for the missing cookie, returns MCPAuth with bearer_token set and
cookie_header None, and the outgoing headers contain Authorization: Bearer
but no Cookie header.

Tests cover both the Builder and Outlook tool paths.
"""

from __future__ import annotations

import logging

import pytest

from pm_agent_system.tools._mcp_jsonrpc import MCPAuth, build_headers, resolve_auth


# ---------------------------------------------------------------------------
# Builder path: MIDWAY_COOKIE_PATH missing, BUILDER_MCP_TOKEN set
# ---------------------------------------------------------------------------


class TestBuilderCookieFallback:
    """Cookie fallback for the Builder MCP auth path."""

    def test_warning_logged_for_missing_cookie(
        self, monkeypatch, tmp_path, caplog
    ):
        """A warning is logged when the cookie file does not exist."""
        missing_cookie = tmp_path / "nonexistent_cookie"
        monkeypatch.setenv("MIDWAY_COOKIE_PATH", str(missing_cookie))
        monkeypatch.setenv("BUILDER_MCP_TOKEN", "test-builder-token")

        with caplog.at_level(logging.WARNING):
            resolve_auth("MIDWAY_COOKIE_PATH", "BUILDER_MCP_TOKEN", logging.getLogger("test"))

        warning_messages = [
            r.message for r in caplog.records if r.levelno >= logging.WARNING
        ]
        assert any("does not exist" in msg for msg in warning_messages), (
            f"Expected a warning about the missing cookie file, "
            f"got warnings: {warning_messages}"
        )

    def test_auth_returns_bearer_token(self, monkeypatch, tmp_path):
        """resolve_auth returns MCPAuth with bearer_token set and cookie_header None."""
        missing_cookie = tmp_path / "nonexistent_cookie"
        monkeypatch.setenv("MIDWAY_COOKIE_PATH", str(missing_cookie))
        monkeypatch.setenv("BUILDER_MCP_TOKEN", "test-builder-token")

        auth = resolve_auth(
            "MIDWAY_COOKIE_PATH", "BUILDER_MCP_TOKEN", logging.getLogger("test")
        )

        assert isinstance(auth, MCPAuth)
        assert auth.bearer_token == "test-builder-token"
        assert auth.cookie_header is None

    def test_headers_contain_authorization_no_cookie(self, monkeypatch, tmp_path):
        """build_headers produces Authorization: Bearer and no Cookie header."""
        missing_cookie = tmp_path / "nonexistent_cookie"
        monkeypatch.setenv("MIDWAY_COOKIE_PATH", str(missing_cookie))
        monkeypatch.setenv("BUILDER_MCP_TOKEN", "test-builder-token")

        auth = resolve_auth(
            "MIDWAY_COOKIE_PATH", "BUILDER_MCP_TOKEN", logging.getLogger("test")
        )
        headers = build_headers(auth)

        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test-builder-token"
        assert "Cookie" not in headers


# ---------------------------------------------------------------------------
# Outlook path: MIDWAY_COOKIE_PATH missing, OUTLOOK_MCP_TOKEN set
# ---------------------------------------------------------------------------


class TestOutlookCookieFallback:
    """Cookie fallback for the Outlook MCP auth path."""

    def test_warning_logged_for_missing_cookie(
        self, monkeypatch, tmp_path, caplog
    ):
        """A warning is logged when the cookie file does not exist."""
        missing_cookie = tmp_path / "nonexistent_cookie"
        monkeypatch.setenv("MIDWAY_COOKIE_PATH", str(missing_cookie))
        monkeypatch.setenv("OUTLOOK_MCP_TOKEN", "test-outlook-token")

        with caplog.at_level(logging.WARNING):
            resolve_auth("MIDWAY_COOKIE_PATH", "OUTLOOK_MCP_TOKEN", logging.getLogger("test"))

        warning_messages = [
            r.message for r in caplog.records if r.levelno >= logging.WARNING
        ]
        assert any("does not exist" in msg for msg in warning_messages), (
            f"Expected a warning about the missing cookie file, "
            f"got warnings: {warning_messages}"
        )

    def test_auth_returns_bearer_token(self, monkeypatch, tmp_path):
        """resolve_auth returns MCPAuth with bearer_token set and cookie_header None."""
        missing_cookie = tmp_path / "nonexistent_cookie"
        monkeypatch.setenv("MIDWAY_COOKIE_PATH", str(missing_cookie))
        monkeypatch.setenv("OUTLOOK_MCP_TOKEN", "test-outlook-token")

        auth = resolve_auth(
            "MIDWAY_COOKIE_PATH", "OUTLOOK_MCP_TOKEN", logging.getLogger("test")
        )

        assert isinstance(auth, MCPAuth)
        assert auth.bearer_token == "test-outlook-token"
        assert auth.cookie_header is None

    def test_headers_contain_authorization_no_cookie(self, monkeypatch, tmp_path):
        """build_headers produces Authorization: Bearer and no Cookie header."""
        missing_cookie = tmp_path / "nonexistent_cookie"
        monkeypatch.setenv("MIDWAY_COOKIE_PATH", str(missing_cookie))
        monkeypatch.setenv("OUTLOOK_MCP_TOKEN", "test-outlook-token")

        auth = resolve_auth(
            "MIDWAY_COOKIE_PATH", "OUTLOOK_MCP_TOKEN", logging.getLogger("test")
        )
        headers = build_headers(auth)

        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test-outlook-token"
        assert "Cookie" not in headers
