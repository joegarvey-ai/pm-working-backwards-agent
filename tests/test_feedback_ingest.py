"""Tests for Slack feedback ingestion.

Ingestion writes locally (output/feedback/), so it is fully testable
headless by mocking only the MCP fetch. The key assertions: a mocked fetch
returning N messages writes N feedback files with valid frontmatter and
status=open, and those files load back via load_all_feedback().
"""

from __future__ import annotations

import argparse
import json
from unittest.mock import patch

import pytest

from pm_agent_system.feedback_inbox import load_all_feedback


@pytest.fixture
def tmp_output(tmp_path, monkeypatch):
    """Point OUTPUT_DIR at a temp dir for both ingest and inbox."""
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    return tmp_path


def _slack_response(n: int) -> str:
    """A plausible slack-mcp get_messages JSON envelope with n messages."""
    messages = [
        {
            "ts": f"171000000{i}.000000",
            "text": f"Stakeholder message number {i}: we should tighten the pricing story.",
            "user": {"real_name": f"Person {i}", "id": f"U0{i}"},
            "permalink": f"https://amazon.enterprise.slack.com/archives/C1/p171000000{i}",
        }
        for i in range(1, n + 1)
    ]
    return json.dumps({"messages": messages})


def _patch_binary_present():
    return patch(
        "pm_agent_system.tools._mcp_stdio.is_binary_available",
        return_value=True,
    )


def _patch_fetch(side_effect):
    return patch(
        "pm_agent_system.feedback_ingest._mcp_stdio.call_stdio_mcp",
        side_effect=side_effect,
    )


class TestFetchSlackFeedback:
    def test_two_messages_write_two_items(self, tmp_output):
        from pm_agent_system.feedback_ingest import fetch_slack_feedback

        with _patch_binary_present(), _patch_fetch(lambda *a, **k: _slack_response(2)):
            ids, err = fetch_slack_feedback(channel="#product-feedback")

        assert err is None
        assert len(ids) == 2

        items = load_all_feedback()
        assert len(items) == 2
        for it in items:
            assert it.status == "open"
            assert it.source.startswith("Slack #product-feedback")
            assert it.raw_text.strip()
            assert "Ingested from Slack" in it.raw_text

    def test_ids_are_unique_and_dated(self, tmp_output):
        from pm_agent_system.feedback_ingest import fetch_slack_feedback

        with _patch_binary_present(), _patch_fetch(lambda *a, **k: _slack_response(3)):
            ids, err = fetch_slack_feedback(channel="C123")

        assert err is None
        assert len(set(ids)) == 3
        assert all(fb_id.startswith("fb-") for fb_id in ids)

    def test_since_passed_through(self, tmp_output):
        from pm_agent_system.feedback_ingest import fetch_slack_feedback

        captured = {}

        def fake(binary, tool, arguments, args=(), timeout=60.0):
            captured["arguments"] = arguments
            return _slack_response(1)

        with _patch_binary_present(), _patch_fetch(fake):
            fetch_slack_feedback(channel="C1", since="2026-07-01")

        assert captured["arguments"]["since"] == "2026-07-01"
        assert captured["arguments"]["channel"] == "C1"

    def test_empty_text_messages_skipped(self, tmp_output):
        from pm_agent_system.feedback_ingest import fetch_slack_feedback

        payload = json.dumps({
            "messages": [
                {"ts": "1710000001.0", "text": "real message", "user": {"real_name": "A"}},
                {"ts": "1710000002.0", "subtype": "channel_join", "user": {"real_name": "B"}},
            ]
        })
        with _patch_binary_present(), _patch_fetch(lambda *a, **k: payload):
            ids, err = fetch_slack_feedback(channel="C1")

        assert err is None
        assert len(ids) == 1

    def test_missing_binary_fails_soft(self, tmp_output):
        from pm_agent_system.feedback_ingest import fetch_slack_feedback

        with patch(
            "pm_agent_system.tools._mcp_stdio.is_binary_available",
            return_value=False,
        ):
            ids, err = fetch_slack_feedback(channel="C1")

        assert ids == []
        assert err is not None
        assert "not found on path" in err.lower()

    def test_transport_error_fails_soft(self, tmp_output):
        from pm_agent_system.feedback_ingest import fetch_slack_feedback

        with _patch_binary_present(), _patch_fetch(RuntimeError("stdio boom")):
            ids, err = fetch_slack_feedback(channel="C1")

        assert ids == []
        assert err is not None and err.lower().startswith("error")

    def test_unparseable_response_yields_no_items_no_error(self, tmp_output):
        from pm_agent_system.feedback_ingest import fetch_slack_feedback

        with _patch_binary_present(), _patch_fetch(lambda *a, **k: "not json at all"):
            ids, err = fetch_slack_feedback(channel="C1")

        assert ids == []
        assert err is None

    def test_bare_array_envelope_supported(self, tmp_output):
        from pm_agent_system.feedback_ingest import fetch_slack_feedback

        payload = json.dumps([{"ts": "1710000001.0", "text": "hi", "user": {"real_name": "A"}}])
        with _patch_binary_present(), _patch_fetch(lambda *a, **k: payload):
            ids, err = fetch_slack_feedback(channel="C1")

        assert err is None
        assert len(ids) == 1


class TestIngestCommand:
    def _ns(self, **over):
        base = dict(command="ingest-feedback", source="slack", channel="#feedback", since="")
        base.update(over)
        return argparse.Namespace(**base)

    def test_command_reports_ids(self, tmp_output, capsys):
        from pm_agent_system.main import cmd_ingest_feedback

        with _patch_binary_present(), _patch_fetch(lambda *a, **k: _slack_response(2)):
            cmd_ingest_feedback(self._ns())

        out = capsys.readouterr().out
        assert "Ingested 2 feedback item(s)" in out

    def test_command_missing_channel_exits(self, tmp_output):
        from pm_agent_system.main import cmd_ingest_feedback

        with pytest.raises(SystemExit):
            cmd_ingest_feedback(self._ns(channel=""))

    def test_command_soft_fails_on_missing_binary(self, tmp_output, capsys):
        from pm_agent_system.main import cmd_ingest_feedback

        with patch(
            "pm_agent_system.tools._mcp_stdio.is_binary_available",
            return_value=False,
        ):
            cmd_ingest_feedback(self._ns())

        # No crash; a descriptive error is printed.
        assert "Error" in capsys.readouterr().out
