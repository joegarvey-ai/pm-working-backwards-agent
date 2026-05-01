"""Output quality eval assertions for the agent harness.

Each function accepts a RunRecord and raises AssertionError with a
descriptive message on failure.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from pm_agent_system.models import (
    BRDOutput,
    CodingPromptOutput,
    PRFAQOutput,
    ResearchOutput,
)
from tests.harness.models import RunRecord

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BANNED_WORDS: list[str] = [
    "robust",
    "comprehensive",
    "powerful",
    "cutting-edge",
    "transformative",
    "game-changing",
    "revolutionary",
    "best-in-class",
    "seamless",
]

# Map task-name substrings to their expected Pydantic output model.
_SCHEMA_MAP: dict[str, type] = {
    "research": ResearchOutput,
    "prfaq": PRFAQOutput,
    "brd": BRDOutput,
    "build_spec": CodingPromptOutput,
    "coding_prompt": CodingPromptOutput,
}


def _match_schema(task_name: str) -> type | None:
    """Return the Pydantic model class that matches *task_name*, or None."""
    lower = task_name.lower()
    for pattern, model_cls in _SCHEMA_MAP.items():
        if pattern in lower:
            return model_cls
    return None


# ---------------------------------------------------------------------------
# Assertion functions
# ---------------------------------------------------------------------------


def assert_schema_valid(record: RunRecord) -> None:
    """Validate each agent output against its expected Pydantic schema.

    The *agent_outputs* dict on the RunRecord maps task names to raw JSON
    strings.  For each entry we attempt to match the task name to one of
    the four output schemas and validate the JSON against it.

    Raises ``AssertionError`` with a descriptive message listing every
    validation failure.
    """
    errors: list[str] = []

    for task_name, raw_json in record.agent_outputs.items():
        model_cls = _match_schema(task_name)
        if model_cls is None:
            # No known schema for this task name; skip silently.
            continue
        try:
            model_cls.model_validate_json(raw_json)
        except (ValidationError, json.JSONDecodeError) as exc:
            errors.append(f"[{task_name}] failed {model_cls.__name__} validation: {exc}")

    if errors:
        raise AssertionError(
            "Schema validation failed for agent outputs:\n" + "\n".join(errors)
        )


def assert_min_content(record: RunRecord) -> None:
    """Check that outputs contain minimum required content.

    * ResearchOutput: at least one source with a non-empty URL
    * PRFAQOutput: non-empty press_release field
    * BRDOutput: at least one functional_requirement
    * CodingPromptOutput: non-empty formatted_spec field

    Raises ``AssertionError`` listing every content deficiency found.
    """
    errors: list[str] = []

    for task_name, raw_json in record.agent_outputs.items():
        model_cls = _match_schema(task_name)
        if model_cls is None:
            continue

        try:
            obj: Any = model_cls.model_validate_json(raw_json)
        except (ValidationError, json.JSONDecodeError):
            # Schema validation is handled by assert_schema_valid; skip here.
            continue

        if isinstance(obj, ResearchOutput):
            has_url = any(
                s.strip() for s in getattr(obj, "sources", []) if s.strip()
            )
            if not has_url:
                errors.append(
                    f"[{task_name}] ResearchOutput has no source with a non-empty URL"
                )

        elif isinstance(obj, PRFAQOutput):
            if not obj.press_release or not obj.press_release.strip():
                errors.append(
                    f"[{task_name}] PRFAQOutput has an empty press_release field"
                )

        elif isinstance(obj, BRDOutput):
            if not obj.functional_requirements:
                errors.append(
                    f"[{task_name}] BRDOutput has no functional_requirements"
                )

        elif isinstance(obj, CodingPromptOutput):
            if not obj.formatted_spec or not obj.formatted_spec.strip():
                errors.append(
                    f"[{task_name}] CodingPromptOutput has an empty formatted_spec field"
                )

    if errors:
        raise AssertionError(
            "Minimum content check failed:\n" + "\n".join(errors)
        )


def assert_no_banned_words(record: RunRecord) -> None:
    """Scan all agent outputs for banned words (case-insensitive).

    Raises ``AssertionError`` listing every occurrence found, including
    the task name, the banned word, and a short context snippet.
    """
    errors: list[str] = []

    for task_name, raw_json in record.agent_outputs.items():
        text_lower = raw_json.lower()
        for word in BANNED_WORDS:
            word_lower = word.lower()
            idx = text_lower.find(word_lower)
            if idx != -1:
                # Extract a short context snippet around the match.
                start = max(0, idx - 30)
                end = min(len(raw_json), idx + len(word) + 30)
                snippet = raw_json[start:end].replace("\n", " ")
                errors.append(
                    f"[{task_name}] banned word '{word}' found: ...{snippet}..."
                )

    if errors:
        raise AssertionError(
            "Banned words found in agent outputs:\n" + "\n".join(errors)
        )
