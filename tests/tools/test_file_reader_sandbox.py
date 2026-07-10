"""Sandbox containment tests for FileReaderTool.

FileReaderTool takes an agent-chosen path and is attached to agents that
also ingest untrusted web content, so it must not read arbitrary files
(credentials, dotfiles) outside the allowed PM-context roots.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pm_agent_system.tools.file_reader import FileReaderTool


def test_reads_file_inside_allowed_root(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    brief = tmp_path / "brief.md"
    brief.write_text("# Product brief\n\nSome context.", encoding="utf-8")

    result = FileReaderTool()._run(str(brief))

    assert "Product brief" in result
    assert "not permitted" not in result


def test_refuses_path_outside_allowed_roots(tmp_path, monkeypatch):
    # Point the allowlist at an empty dir, then try to read a sibling
    # outside it (stands in for ~/.aws/credentials, /etc/passwd, etc.).
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(allowed))
    monkeypatch.setenv("PM_AGENT_CONTEXT_DIRS", "")
    monkeypatch.chdir(allowed)

    outside = tmp_path / "outside_secret.txt"
    outside.write_text("SENSITIVE", encoding="utf-8")

    result = FileReaderTool()._run(str(outside))

    assert "not permitted" in result
    assert "SENSITIVE" not in result


def test_refuses_traversal_escape(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(allowed))
    monkeypatch.setenv("PM_AGENT_CONTEXT_DIRS", "")
    monkeypatch.chdir(allowed)

    secret = tmp_path / "creds.txt"
    secret.write_text("SENSITIVE", encoding="utf-8")

    # A ../ traversal that resolves outside the allowed root is refused.
    result = FileReaderTool()._run(str(allowed / ".." / "creds.txt"))

    assert "not permitted" in result
    assert "SENSITIVE" not in result


def test_refuses_credential_filename_even_inside_root(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=sk-ant-secret", encoding="utf-8")

    result = FileReaderTool()._run(str(env_file))

    assert "not permitted" in result
    assert "sk-ant-secret" not in result


def test_context_dirs_env_widens_allowlist(tmp_path, monkeypatch):
    extra = tmp_path / "extra_context"
    extra.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "unrelated"))
    monkeypatch.setenv("PM_AGENT_CONTEXT_DIRS", str(extra))

    doc = extra / "notes.md"
    doc.write_text("# Notes", encoding="utf-8")

    result = FileReaderTool()._run(str(doc))

    assert "Notes" in result
    assert "not permitted" not in result
