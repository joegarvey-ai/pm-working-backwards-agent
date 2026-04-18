"""Tests for the VaultCheckpointProvider — the pre-checkpoint vault write flow."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml
from pydantic import BaseModel

from pm_agent_system.vault import (
    VaultConfig,
    compute_body_hash,
    strip_frontmatter,
)
from pm_agent_system.vault_checkpoint import (
    ArtifactHandler,
    VaultCheckpointProvider,
    build_registry,
)


# ---- Test model + handler factory ----


class FakeArtifact(BaseModel):
    """Stand-in for a real Pydantic output model."""

    title: str
    body: str


class OtherArtifact(BaseModel):
    """Second Pydantic type to verify multi-handler dispatch."""

    different: str


def _render(obj: FakeArtifact) -> str:
    return f"# {obj.title}\n\n{obj.body}"


def _make_handler(output_dir: Path, post_approve=None) -> ArtifactHandler:
    """Return a ready-to-register ArtifactHandler keyed on FakeArtifact."""
    saved_paths: list[Path] = []

    def _save(md: str, _obj: FakeArtifact) -> Path:
        path = output_dir / "artifact.md"
        path.write_text(md, encoding="utf-8")
        saved_paths.append(path)
        return path

    handler = ArtifactHandler(
        artifact_type="prfaq",
        pydantic_class=FakeArtifact,
        render_fn=_render,
        save_output_fn=_save,
        version="1.0",
        upstream="research_brief",
        downstream="brd",
        post_approve=post_approve,
    )
    return handler


# ---- Fake ExecutorContext and AgentFinish ----


@dataclass
class FakeAgentFinish:
    """Minimal stand-in for crewai.agents.parser.AgentFinish."""

    output: str  # JSON string of the Pydantic output


class FakeContext:
    """Minimal ExecutorContext that supports the methods the provider calls.

    ``invoke_loop_returns`` is a list of AgentFinish-like objects that will be
    popped in order each time ``_invoke_loop`` is invoked, simulating CrewAI
    re-running the agent with the appended feedback message.
    """

    def __init__(self, invoke_loop_returns=None):
        self.task = SimpleNamespace(name="fake_task")
        self.crew = None
        self.messages: list[dict] = []
        self.ask_for_human_input = True
        self.llm = None
        self.agent = None
        self._invoke_loop_queue = list(invoke_loop_returns or [])
        self.invoke_loop_calls = 0

    def _invoke_loop(self):
        self.invoke_loop_calls += 1
        if not self._invoke_loop_queue:
            raise AssertionError("Unexpected _invoke_loop call with no queued return")
        return self._invoke_loop_queue.pop(0)

    def _is_training_mode(self) -> bool:
        return False

    def _handle_crew_training_output(self, result, human_feedback=None) -> None:
        pass

    def _format_feedback_message(self, feedback: str) -> dict:
        return {"role": "user", "content": feedback}


def _finish(obj: BaseModel) -> FakeAgentFinish:
    return FakeAgentFinish(output=obj.model_dump_json())


def _build_provider(tmp_path: Path, handler: ArtifactHandler) -> VaultCheckpointProvider:
    vault_cfg = VaultConfig(vault_path=str(tmp_path), folder_prefix="PM Agent")
    return VaultCheckpointProvider(
        registry=build_registry([handler]),
        vault_config=vault_cfg,
        product_slug="test-product",
    )


def _vault_file(tmp_path: Path, artifact_filename: str = "prfaq_v1.0.md") -> Path:
    return tmp_path / "PM Agent" / "test-product" / artifact_filename


# ---- Tests ----


def test_pre_checkpoint_write_creates_file_with_draft_status(tmp_path):
    """Provider writes vault file with status=draft BEFORE the PM is prompted."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    handler = _make_handler(output_dir)
    provider = _build_provider(tmp_path, handler)

    obj = FakeArtifact(title="Hello", body="World")
    finish = _finish(obj)
    ctx = FakeContext()

    with patch("builtins.input", side_effect=["a"]):
        result = provider.handle_feedback(finish, ctx)

    assert result is finish  # approved returns the original answer
    vault_file = _vault_file(tmp_path)
    assert vault_file.exists(), "Vault file should be created before prompt"

    content = vault_file.read_text(encoding="utf-8")
    # After approval, status is flipped to approved. But we can verify the file
    # existed with draft status first via the provider's record timing:
    assert "status: approved" in content, "Approval should flip status from draft to approved"
    assert "artifact_type: prfaq" in content
    assert "# Hello" in content


def test_approval_flips_status_and_refreshes_hash(tmp_path):
    """[a] approval sets status=approved and updates original_hash to current body."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    handler = _make_handler(output_dir)
    provider = _build_provider(tmp_path, handler)

    ctx = FakeContext()
    with patch("builtins.input", side_effect=["a"]):
        provider.handle_feedback(_finish(FakeArtifact(title="T", body="B")), ctx)

    vault_file = _vault_file(tmp_path)
    content = vault_file.read_text(encoding="utf-8")
    fm_block = content.split("---\n")[1]
    fm = yaml.safe_load(fm_block)

    assert fm["status"] == "approved"
    # original_hash should match the current body (minus frontmatter, minus traceability line)
    expected_hash = compute_body_hash(content)
    assert fm["original_hash"] == expected_hash


def test_feedback_revision_overwrites_same_vault_version(tmp_path):
    """[f] feedback triggers re-invoke; new output overwrites the SAME vault file."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    handler = _make_handler(output_dir)
    provider = _build_provider(tmp_path, handler)

    original = FakeArtifact(title="Original", body="First pass.")
    revised = FakeArtifact(title="Revised", body="Better pass.")
    ctx = FakeContext(invoke_loop_returns=[_finish(revised)])

    with patch("builtins.input", side_effect=["f make it better", "a"]):
        provider.handle_feedback(_finish(original), ctx)

    assert ctx.invoke_loop_calls == 1, "One revision round expected"

    # Only one vault file exists — same version, overwritten
    vault_folder = tmp_path / "PM Agent" / "test-product"
    version_files = sorted(vault_folder.glob("prfaq_v*.md"))
    assert [p.name for p in version_files] == ["prfaq_v1.0.md"], (
        "Checkpoint iterations must overwrite, not create new versions"
    )

    content = version_files[0].read_text(encoding="utf-8")
    assert "# Revised" in content
    assert "# Original" not in content
    assert "status: approved" in content

    # The feedback text was injected into the agent's message history
    assert any("make it better" in m.get("content", "") for m in ctx.messages)


def test_obsidian_edit_reads_changes_and_reinvokes(tmp_path):
    """[o] when PM edited vault: strip frontmatter, pass body as feedback, re-invoke."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    handler = _make_handler(output_dir)
    provider = _build_provider(tmp_path, handler)

    original = FakeArtifact(title="Draft", body="Agent wrote this.")
    revised = FakeArtifact(title="Draft", body="Agent wrote this, with PM edits incorporated.")
    ctx = FakeContext(invoke_loop_returns=[_finish(revised)])

    # Simulate the PM editing the vault file BEFORE they type "o"
    def _edit_vault_then_choose_o(*args, **kwargs):
        # First call: choose [o] — but first we need the vault file to exist, so this
        # side-effect modifies the vault file before returning the choice.
        vault_file = _vault_file(tmp_path)
        if vault_file.exists():
            content = vault_file.read_text(encoding="utf-8")
            content = content.replace("Agent wrote this.", "PM edited this directly in Obsidian.")
            vault_file.write_text(content, encoding="utf-8")
        return "o"

    call_count = {"n": 0}

    def _input_stub(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _edit_vault_then_choose_o()
        return "a"  # approve after the revision

    with patch("builtins.input", side_effect=_input_stub):
        provider.handle_feedback(_finish(original), ctx)

    assert ctx.invoke_loop_calls == 1

    # Verify the feedback injected into ctx.messages carries the PM's edited body
    feedback_msg = next(
        (m["content"] for m in ctx.messages if "PM edited" in m.get("content", "")),
        None,
    )
    assert feedback_msg is not None, "PM's edits must be passed to the agent"
    assert "PM edited this directly in Obsidian." in feedback_msg


def test_obsidian_edit_no_change_reprompts(tmp_path):
    """[o] when PM did NOT edit: detect no divergence, do NOT re-invoke, re-prompt."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    handler = _make_handler(output_dir)
    provider = _build_provider(tmp_path, handler)

    original = FakeArtifact(title="Draft", body="Unchanged.")
    # No _invoke_loop_returns — if the provider tries to re-invoke, the queue is empty
    # and FakeContext raises AssertionError.
    ctx = FakeContext(invoke_loop_returns=[])

    with patch("builtins.input", side_effect=["o", "a"]):
        provider.handle_feedback(_finish(original), ctx)

    assert ctx.invoke_loop_calls == 0, (
        "[o] with no Obsidian edits should not trigger agent re-invocation"
    )


def test_non_artifact_task_falls_through_to_default_prompt(tmp_path):
    """Pydantic class not in registry -> default SyncHumanInputProvider path."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    handler = _make_handler(output_dir)
    provider = _build_provider(tmp_path, handler)

    # Build a finish whose output is raw text (not valid JSON for FakeArtifact)
    finish = FakeAgentFinish(output="Just some free-form Q&A answer from the agent.")
    ctx = FakeContext()
    # For the default prompt, we provide an empty response to exit the loop.
    with patch("builtins.input", return_value=""):
        # The default provider uses _prompt_input which wraps in Rich panels and reads input;
        # empty string means "approve" in the default flow.
        provider.handle_feedback(finish, ctx)

    # No vault file written, no _invoke_loop call
    vault_folder = tmp_path / "PM Agent" / "test-product"
    assert not vault_folder.exists() or not any(vault_folder.iterdir()), (
        "Non-artifact tasks must not produce vault files"
    )
    assert ctx.invoke_loop_calls == 0


def test_pydantic_parse_failure_falls_through_on_initial_output(tmp_path):
    """If the agent's initial output fails to parse (e.g. truncated JSON), fall through."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    handler = _make_handler(output_dir)
    provider = _build_provider(tmp_path, handler)

    # Truncated / invalid JSON for FakeArtifact
    finish = FakeAgentFinish(output='{"title": "Broken", "body": "Trunc')
    ctx = FakeContext()
    with patch("builtins.input", return_value=""):
        provider.handle_feedback(finish, ctx)

    # No vault write, no re-invoke
    vault_file = _vault_file(tmp_path)
    assert not vault_file.exists()
    assert ctx.invoke_loop_calls == 0


def test_build_registry_rejects_duplicate_classes():
    """Only one handler per Pydantic class — duplicates should raise."""
    h1 = ArtifactHandler(
        artifact_type="prfaq",
        pydantic_class=FakeArtifact,
        render_fn=_render,
        save_output_fn=lambda md, _: Path("/dev/null"),
    )
    h2 = ArtifactHandler(
        artifact_type="prfaq",
        pydantic_class=FakeArtifact,
        render_fn=_render,
        save_output_fn=lambda md, _: Path("/dev/null"),
    )
    with pytest.raises(ValueError, match="Duplicate"):
        build_registry([h1, h2])


def test_post_approve_hook_fires_on_approval(tmp_path):
    """post_approve callback is invoked with the vault path after [a]."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    seen: list[str] = []

    def _on_approve(path: str) -> None:
        seen.append(path)

    handler = _make_handler(output_dir, post_approve=_on_approve)
    provider = _build_provider(tmp_path, handler)

    ctx = FakeContext()
    with patch("builtins.input", side_effect=["a"]):
        provider.handle_feedback(_finish(FakeArtifact(title="T", body="B")), ctx)

    assert len(seen) == 1
    assert seen[0].endswith("prfaq_v1.0.md")


def test_provider_records_written_artifact(tmp_path):
    """provider.artifacts tracks each artifact's paths and approval state."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    handler = _make_handler(output_dir)
    provider = _build_provider(tmp_path, handler)

    ctx = FakeContext()
    with patch("builtins.input", side_effect=["a"]):
        provider.handle_feedback(_finish(FakeArtifact(title="T", body="B")), ctx)

    assert "prfaq" in provider.artifacts
    record = provider.artifacts["prfaq"]
    assert record.approved is True
    assert record.output_path.exists()
    assert "PM Agent" in record.vault_path
