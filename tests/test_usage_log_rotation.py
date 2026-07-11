"""Tests for the size-bounded usage-log writer (_append_usage_log)."""

from __future__ import annotations

import json
from pathlib import Path

from pm_agent_system.main import _append_usage_log


def test_appends_one_line_per_call(tmp_path: Path) -> None:
    log = tmp_path / "usage_log.jsonl"
    _append_usage_log({"a": 1}, log)
    _append_usage_log({"b": 2}, log)

    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"a": 1}
    assert json.loads(lines[1]) == {"b": 2}


def test_rotates_on_size(tmp_path: Path) -> None:
    log = tmp_path / "usage_log.jsonl"
    # Each entry is ~9 bytes; a 20-byte cap forces a rotation within a few writes.
    for i in range(5):
        _append_usage_log({"i": i}, log, max_bytes=20)

    backup = tmp_path / "usage_log.jsonl.1"
    assert log.exists()
    assert backup.exists()
    # The live file was reset at rotation, so it stays near the cap, not unbounded.
    assert log.stat().st_size < 20 + 100


def test_keeps_single_backup(tmp_path: Path) -> None:
    log = tmp_path / "usage_log.jsonl"
    for i in range(12):
        _append_usage_log({"i": i}, log, max_bytes=40)

    # Only the live file and one backup exist; no .2, .3, ...
    siblings = sorted(p.name for p in tmp_path.iterdir())
    assert siblings == ["usage_log.jsonl", "usage_log.jsonl.1"]


def test_oserror_is_swallowed(tmp_path: Path) -> None:
    # Parent directory does not exist -> open() raises OSError, which the
    # helper must swallow so logging never fails a real run.
    missing = tmp_path / "nope" / "usage_log.jsonl"
    _append_usage_log({"a": 1}, missing)  # must not raise
    assert not missing.exists()
