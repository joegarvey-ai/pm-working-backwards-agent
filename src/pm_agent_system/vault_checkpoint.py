"""Custom CrewAI HumanInputProvider that publishes artifacts to the vault BEFORE the PM is prompted.

With this provider registered, every artifact-producing task checkpoint becomes a
"publish then review" flow:

  1. Agent produces output
  2. Provider parses output against registered Pydantic classes
  3. Provider renders markdown, writes to output/ and to the Obsidian vault (status: draft)
  4. Terminal prints file paths and the [a]/[f]/[o] prompt
  5. PM reviews in Obsidian or terminal, then chooses:
       [a]  Approve  -> vault status flips to "approved" and original_hash refreshes
       [f]  Feedback -> agent revises, same vault file overwritten
       [o]  Obsidian edit -> PM's edits read back as revision context

For any task whose output does not match a registered Pydantic class (e.g. the
``validate_input`` challenge Q&A), the provider falls through to CrewAI's default
SyncHumanInputProvider behavior.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from crewai.core.providers.human_input import SyncHumanInputProvider
from pydantic import BaseModel

from pm_agent_system.vault import (
    VaultConfig,
    approve_vault_artifact,
    detect_divergence,
    strip_frontmatter,
    write_to_vault,
)

logger = logging.getLogger(__name__)


ARTIFACT_DISPLAY_NAMES = {
    "research_brief": "Research brief",
    "prfaq": "PRFAQ",
    "design_brief": "Design brief",
    "brd": "BRD",
    "build_spec": "Build spec",
}


@dataclass
class ArtifactHandler:
    """Per-task configuration for how to write an artifact during a checkpoint.

    - ``version`` may be a string or a callable of the parsed Pydantic object
      (e.g. to read ``obj.version_history[-1].version``).
    - ``save_output_fn`` writes the markdown to ``output/`` and returns either a
      single ``Path`` or a tuple ``(primary_path, *extra_paths)``.
    - ``post_approve`` is invoked with the vault path after the PM approves; used
      for e.g. marking the previous version as superseded on standalone revisions.
    """

    artifact_type: str  # "research_brief" | "prfaq" | "brd" | "build_spec"
    pydantic_class: type[BaseModel]
    render_fn: Callable[[BaseModel], str]
    save_output_fn: Callable[[str, BaseModel], Any]
    version: str | Callable[[BaseModel], str] = "1.0"
    upstream: str | None = None
    downstream: str | None = None
    post_approve: Callable[[str], None] | None = None


@dataclass
class WrittenArtifact:
    """Records where an artifact was written during the run."""

    artifact_type: str
    output_path: Path
    vault_path: str
    extras: list[Path] = field(default_factory=list)
    approved: bool = False


class VaultCheckpointProvider(SyncHumanInputProvider):
    """Writes artifacts to output/ and the Obsidian vault before each human_input pause.

    The registry is keyed by Pydantic output class because CrewAI Task names are not
    reliably populated for inline-built tasks (tasks created via ``Task(config=...)``
    in ``crew.py`` crews like ``research_and_generate_crew``). Pydantic classes are
    unique per artifact type and set on every task via ``output_pydantic``.
    """

    def __init__(
        self,
        registry: dict[type[BaseModel], ArtifactHandler],
        vault_config: VaultConfig | None,
        product_slug: str,
    ) -> None:
        self.registry = registry
        self.vault_config = vault_config
        self.product_slug = product_slug
        self.artifacts: dict[str, WrittenArtifact] = {}

    # ---- Protocol entrypoint ----

    def handle_feedback(self, formatted_answer, context):  # type: ignore[override]
        handler, parsed = self._match_handler(formatted_answer)
        if handler is None or parsed is None:
            # Non-artifact task, or Pydantic parse failed (e.g. truncated output).
            # Fall through to CrewAI's default prompt so the PM still sees the output
            # and can approve or give feedback.
            return super().handle_feedback(formatted_answer, context)

        return self._run_checkpoint_loop(formatted_answer, parsed, handler, context)

    # ---- Internals ----

    def _match_handler(self, formatted_answer) -> tuple[ArtifactHandler | None, BaseModel | None]:
        """Try to parse formatted_answer.output against each registered Pydantic class."""
        raw = self._get_output_string(formatted_answer)
        for pydantic_class, handler in self.registry.items():
            try:
                parsed = pydantic_class.model_validate_json(raw)
                return handler, parsed
            except Exception:
                continue
        return None, None

    def _resolve_version(self, handler: ArtifactHandler, parsed: BaseModel) -> str:
        if callable(handler.version):
            try:
                return handler.version(parsed)
            except Exception as exc:
                logger.warning(
                    "version resolver for %s raised %s; falling back to 1.0",
                    handler.artifact_type, exc,
                )
                return "1.0"
        return handler.version

    def _write_artifact(
        self, markdown: str, parsed: BaseModel, handler: ArtifactHandler
    ) -> WrittenArtifact:
        """Write to output/ and vault. Records paths in self.artifacts."""
        save_result = handler.save_output_fn(markdown, parsed)
        if isinstance(save_result, tuple):
            output_path = Path(save_result[0])
            extras = [Path(p) for p in save_result[1:]]
        else:
            output_path = Path(save_result)
            extras = []

        version = self._resolve_version(handler, parsed)
        vault_path = ""
        if self.vault_config:
            vault_path = write_to_vault(
                markdown_content=markdown,
                artifact_type=handler.artifact_type,
                product_slug=self.product_slug,
                version=version,
                vault_config=self.vault_config,
                upstream=handler.upstream,
                downstream=handler.downstream,
            )

        record = WrittenArtifact(
            artifact_type=handler.artifact_type,
            output_path=output_path,
            vault_path=vault_path,
            extras=extras,
            approved=False,
        )
        self.artifacts[handler.artifact_type] = record
        return record

    def _run_checkpoint_loop(self, formatted_answer, parsed, handler: ArtifactHandler, context):
        """Write, prompt, dispatch — looping until [a] approves."""
        while True:
            markdown = handler.render_fn(parsed)
            record = self._write_artifact(markdown, parsed, handler)

            choice, feedback_text = self._prompt_checkpoint(handler, record)

            if choice == "approve":
                if record.vault_path:
                    approve_vault_artifact(record.vault_path)
                    record.approved = True
                    if handler.post_approve:
                        try:
                            handler.post_approve(record.vault_path)
                        except Exception as exc:
                            logger.warning("post_approve hook raised %s", exc)
                context.ask_for_human_input = False
                return formatted_answer

            if choice == "feedback":
                context.messages.append(context._format_feedback_message(feedback_text))
                formatted_answer = context._invoke_loop()
                parsed = self._reparse_or_bail(formatted_answer, handler, context)
                if parsed is None:
                    # Parse failed — hand off to default prompt so PM still gets the output
                    return super().handle_feedback(formatted_answer, context)
                continue

            if choice == "obsidian_edit":
                if not record.vault_path:
                    print("Vault is not configured — cannot read Obsidian edits.")
                    continue
                div = detect_divergence(record.vault_path)
                if not div.diverged:
                    print(
                        "\nNo changes detected in the vault file. "
                        "Try [a] to approve, [f] for feedback, "
                        "or [o] again after editing in Obsidian."
                    )
                    continue
                pm_body = strip_frontmatter(
                    Path(record.vault_path).read_text(encoding="utf-8")
                )
                feedback = _build_obsidian_edit_feedback(pm_body)
                context.messages.append(context._format_feedback_message(feedback))
                formatted_answer = context._invoke_loop()
                parsed = self._reparse_or_bail(formatted_answer, handler, context)
                if parsed is None:
                    return super().handle_feedback(formatted_answer, context)
                continue

    def _reparse_or_bail(self, formatted_answer, handler: ArtifactHandler, context) -> BaseModel | None:
        """Reparse a revised output; return the Pydantic or None if parsing failed."""
        raw = self._get_output_string(formatted_answer)
        try:
            return handler.pydantic_class.model_validate_json(raw)
        except Exception as exc:
            logger.warning(
                "Pydantic parse failed on revised %s output: %s",
                handler.artifact_type, exc,
            )
            print(
                f"\nCouldn't parse the revised {handler.artifact_type} as a "
                f"structured object (likely truncated). Falling back to the "
                f"default review prompt so you can still approve or give feedback."
            )
            return None

    # ---- UI ----

    def _prompt_checkpoint(
        self, handler: ArtifactHandler, record: WrittenArtifact
    ) -> tuple[str, str]:
        display = ARTIFACT_DISPLAY_NAMES.get(handler.artifact_type, handler.artifact_type)
        print(f"\n{display} draft published.")
        print(f"  -> {record.output_path}")
        if record.vault_path:
            short = _shorten_vault_path(record.vault_path)
            print(f"  -> {short}  (Obsidian)")
        print()
        print("Review the draft above or in Obsidian, then:")
        print("  [a]  Approve and continue")
        print("  [f]  Provide feedback (follow with your feedback text)")
        if record.vault_path:
            print("  [o]  I edited the file in Obsidian — read my changes and revise")
        print()

        while True:
            try:
                resp = input("> ").strip()
            except EOFError:
                # Non-interactive context — treat as approve so the pipeline can finish
                return ("approve", "")
            if not resp:
                continue
            head = resp[0].lower()
            if head == "a":
                return ("approve", "")
            if head == "f":
                rest = resp[1:].strip()
                if not rest:
                    rest = input("Feedback: ").strip()
                if not rest:
                    print("Feedback cannot be empty — type your feedback, or select [a] to approve.")
                    continue
                return ("feedback", rest)
            if head == "o" and record.vault_path:
                return ("obsidian_edit", "")
            print("Please respond with [a], [f <text>], or [o].")


# ---- Helpers ----


def _shorten_vault_path(vault_path: str) -> str:
    """Return a short, recognisable portion of the vault path (starting at 'PM Agent')."""
    p = Path(vault_path)
    for i, part in enumerate(p.parts):
        if part == "PM Agent":
            return "/".join(p.parts[i:])
    return str(p)


def _build_obsidian_edit_feedback(pm_body: str) -> str:
    """Construct the revision instruction passed to the agent when the PM selects [o]."""
    return (
        "The PM edited the draft directly in their Obsidian vault. "
        "Below is the PM's edited version of the document. "
        "Produce a revised version that incorporates the PM's edits — "
        "preserve their wording and structural choices where they made them, "
        "and you may further improve clarity, completeness, or structure "
        "where appropriate.\n\n"
        "---- BEGIN PM-EDITED VERSION ----\n\n"
        f"{pm_body}\n\n"
        "---- END PM-EDITED VERSION ----"
    )


# ---- Convenience: collect registry entries ----


def build_registry(handlers: Iterable[ArtifactHandler]) -> dict[type[BaseModel], ArtifactHandler]:
    """Turn a list of handlers into a class->handler dict, guarding against duplicate classes."""
    registry: dict[type[BaseModel], ArtifactHandler] = {}
    for h in handlers:
        if h.pydantic_class in registry:
            raise ValueError(
                f"Duplicate registry entry for {h.pydantic_class.__name__}: "
                f"only one handler per Pydantic class is supported."
            )
        registry[h.pydantic_class] = h
    return registry
