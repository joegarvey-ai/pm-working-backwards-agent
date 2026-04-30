"""Unit tests for extract_text and log_call from _mcp_jsonrpc.

Validates: Requirements 7.6
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pm_agent_system.tools._mcp_jsonrpc import extract_text, log_call


# ---------------------------------------------------------------------------
# extract_text tests
# ---------------------------------------------------------------------------


class TestExtractText:
    """Tests for extract_text on representative MCP response shapes."""

    def test_single_text_content_item(self) -> None:
        response = {
            "result": {
                "content": [{"type": "text", "text": "Hello world"}],
            },
        }
        assert extract_text(response) == "Hello world"

    def test_multiple_text_content_items_joined(self) -> None:
        response = {
            "result": {
                "content": [
                    {"type": "text", "text": "First"},
                    {"type": "text", "text": "Second"},
                    {"type": "text", "text": "Third"},
                ],
            },
        }
        assert extract_text(response) == "First\n\n---\n\nSecond\n\n---\n\nThird"

    def test_empty_content_list(self) -> None:
        response = {"result": {"content": []}}
        assert extract_text(response) == ""

    def test_missing_result_key(self) -> None:
        response = {"id": 1, "jsonrpc": "2.0"}
        assert extract_text(response) == ""

    def test_missing_content_key(self) -> None:
        response = {"result": {"other_key": "value"}}
        assert extract_text(response) == ""

    def test_non_dict_input_returns_empty(self) -> None:
        assert extract_text("not a dict") == ""  # type: ignore[arg-type]
        assert extract_text(42) == ""  # type: ignore[arg-type]
        assert extract_text(None) == ""  # type: ignore[arg-type]
        assert extract_text([1, 2, 3]) == ""  # type: ignore[arg-type]

    def test_content_items_without_text_key_skipped(self) -> None:
        response = {
            "result": {
                "content": [
                    {"type": "image", "url": "http://example.com/img.png"},
                    {"type": "text", "text": "Only text"},
                ],
            },
        }
        assert extract_text(response) == "Only text"

    def test_content_items_with_empty_text_skipped(self) -> None:
        response = {
            "result": {
                "content": [
                    {"type": "text", "text": ""},
                    {"type": "text", "text": "Non-empty"},
                ],
            },
        }
        assert extract_text(response) == "Non-empty"


# ---------------------------------------------------------------------------
# log_call tests
# ---------------------------------------------------------------------------


class TestLogCall:
    """Tests for log_call JSONL logging behaviour."""

    def test_writes_exactly_one_json_line(self, tmp_path: Path) -> None:
        log_file = tmp_path / "calls.log"
        log_call(log_file, "invocation", {"tool": "builder_mcp", "query": "test"})

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 1

        entry = json.loads(lines[0])
        assert "timestamp" in entry
        assert entry["event"] == "invocation"
        assert entry["tool"] == "builder_mcp"
        assert entry["query"] == "test"

    def test_multiple_calls_append_separate_lines(self, tmp_path: Path) -> None:
        log_file = tmp_path / "calls.log"
        log_call(log_file, "invocation", {"action": "wiki_search"})
        log_call(log_file, "response", {"chars": 150})

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 2

        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert first["event"] == "invocation"
        assert second["event"] == "response"

    def test_each_line_has_required_keys(self, tmp_path: Path) -> None:
        log_file = tmp_path / "calls.log"
        details = {"key1": "val1", "key2": 42}
        log_call(log_file, "test_event", details)

        entry = json.loads(log_file.read_text().strip())
        assert "timestamp" in entry
        assert "event" in entry
        assert entry["key1"] == "val1"
        assert entry["key2"] == 42

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        log_file = tmp_path / "nested" / "deep" / "calls.log"
        log_call(log_file, "invocation", {"msg": "hello"})

        assert log_file.exists()
        entry = json.loads(log_file.read_text().strip())
        assert entry["event"] == "invocation"

    def test_swallows_oserror_on_mkdir(self, tmp_path: Path) -> None:
        log_file = tmp_path / "subdir" / "calls.log"

        with patch.object(Path, "mkdir", side_effect=OSError("Permission denied")):
            # Should not raise
            log_call(log_file, "invocation", {"msg": "should not crash"})

        # File should not have been created since mkdir failed
        assert not log_file.exists()

    def test_swallows_generic_exception(self, tmp_path: Path) -> None:
        log_file = tmp_path / "calls.log"

        with patch("builtins.open", side_effect=RuntimeError("unexpected")):
            # Should not raise
            log_call(log_file, "invocation", {"msg": "should not crash"})
