"""Integration tests: pipeline accepts markdown and YAML inputs and copies the
brief into the vault when ``OBSIDIAN_VAULT_PATH`` is configured."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.test_full_pipeline_save import _build_mock_result


# ---------- Fixtures ----------


@pytest.fixture
def output_dir(tmp_path, monkeypatch):
    """Patch OUTPUT_DIR and clear OBSIDIAN_VAULT_PATH by default."""
    out = tmp_path / "output"
    out.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(out))
    monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)
    return out


@pytest.fixture
def yaml_input(tmp_path) -> str:
    import yaml
    data = {
        "product_name": "Pipeline Test",
        "feature_summary": "Test Feature",
        "goals": "Test goals",
        "timing": "Q3 2026",
        "user_summary": "Test users",
    }
    path = tmp_path / "input.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return str(path)


@pytest.fixture
def markdown_input(tmp_path) -> str:
    content = """# Product Input Brief

## Product Name

Pipeline Test

## Feature / Idea Summary

Test Feature

## Goals

Test goals

## Target Users

Test users

## Timing

Q3 2026
"""
    path = tmp_path / "input.md"
    path.write_text(content, encoding="utf-8")
    return str(path)


def _run_full_pipeline(input_file: str) -> None:
    """Invoke cmd_full_pipeline with kickoff mocked to fire task callbacks."""
    mock_result = _build_mock_result()

    with patch("pm_agent_system.main.PmAgentSystem") as MockCrew:
        instance = MockCrew.return_value
        crew_mock = MagicMock()

        def _kickoff_with_callbacks(**_kwargs):
            if crew_mock.task_callback:
                for task_output in mock_result.tasks_output:
                    crew_mock.task_callback(task_output)
            return mock_result

        crew_mock.kickoff.side_effect = _kickoff_with_callbacks
        instance.full_pipeline_crew.return_value = crew_mock

        from pm_agent_system.main import cmd_full_pipeline

        args = argparse.Namespace(
            input_file=input_file,
            target_tool="kiro",
            requirements_path=None,
            skip_validation=False,
            resume=False,
            fresh=False,
        )
        cmd_full_pipeline(args)


# ---------- Pipeline accepts both formats ----------


def test_full_pipeline_accepts_markdown_input(output_dir: Path, markdown_input: str) -> None:
    _run_full_pipeline(markdown_input)
    names = [p.name for p in output_dir.iterdir() if p.is_file()]
    assert any(n.startswith("research_brief") and n.endswith(".md") for n in names), names
    assert any(n.startswith("prfaq_") and n.endswith(".md") for n in names), names
    assert any(n.startswith("brd_") and n.endswith(".md") for n in names), names


def test_full_pipeline_accepts_yaml_input(output_dir: Path, yaml_input: str) -> None:
    """Regression: existing YAML input flow must still produce all artifacts."""
    _run_full_pipeline(yaml_input)
    names = [p.name for p in output_dir.iterdir() if p.is_file()]
    assert any(n.startswith("research_brief") and n.endswith(".md") for n in names), names
    assert any(n.startswith("prfaq_") and n.endswith(".md") for n in names), names
    assert any(n.startswith("brd_") and n.endswith(".md") for n in names), names


# ---------- Vault copy of the input brief ----------


def test_input_brief_copied_to_vault(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    markdown_input: str,
) -> None:
    """When the vault is configured and input is .md, the brief is copied into
    the product folder as input_brief.md with the expected frontmatter."""
    out = tmp_path / "output"
    out.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(out))
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))
    monkeypatch.delenv("OBSIDIAN_FOLDER_PREFIX", raising=False)

    _run_full_pipeline(markdown_input)

    # Product slug derived from "Pipeline Test" → "pipeline-test"
    brief_path = vault / "PM Agent" / "pipeline-test" / "input_brief.md"
    assert brief_path.exists(), (
        f"input_brief.md missing. Vault tree: "
        f"{[str(p.relative_to(vault)) for p in vault.rglob('*') if p.is_file()]}"
    )

    text = brief_path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "missing frontmatter delimiter"
    head, _, _body = text.partition("\n---\n")
    fm_block = head + "\n---\n"
    assert "artifact_type: input_brief" in fm_block
    assert "status: active" in fm_block
    assert "product_slug: pipeline-test" in fm_block

    # Body should preserve the markdown content (the h2 headings)
    assert "## Product Name" in text
    assert "Pipeline Test" in text


def test_input_brief_yaml_source_wrapped_in_code_fence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    yaml_input: str,
) -> None:
    """YAML inputs are still copied to the vault, wrapped in a YAML code block
    so they're readable in Obsidian."""
    out = tmp_path / "output"
    out.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(out))
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))

    _run_full_pipeline(yaml_input)

    brief_path = vault / "PM Agent" / "pipeline-test" / "input_brief.md"
    assert brief_path.exists()
    text = brief_path.read_text(encoding="utf-8")
    assert "artifact_type: input_brief" in text
    assert "```yaml" in text
    assert "feature_summary" in text
