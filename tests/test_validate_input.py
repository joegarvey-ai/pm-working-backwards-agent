"""Regression tests for ``validate_input`` null/empty-field handling.

Covers the bug where ``parse_markdown_input`` returns ``None`` for a section
whose header exists but contains no content after HTML-comment stripping,
and ``validate_input`` previously crashed with ``AttributeError`` because
``dict.get(key, "")`` only returns the default for *absent* keys — a
present key with value ``None`` passes through.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pm_agent_system.input_parser import parse_input
from pm_agent_system.main import ENCOURAGED_FIELDS, REQUIRED_FIELDS, validate_input


REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = REPO_ROOT / "examples"


def _full_inputs(**overrides) -> dict:
    """Return a dict with every REQUIRED and ENCOURAGED field populated."""
    base = {f: f"{f} value" for f in REQUIRED_FIELDS + ENCOURAGED_FIELDS}
    base.update(overrides)
    return base


# ---------- Required fields: None / empty / whitespace → treated like missing ----------


def test_validate_input_tolerates_none_value_in_required():
    """A required field set to None must surface as a missing-field error, not a crash."""
    inputs = _full_inputs(feature_summary=None)
    with pytest.raises(SystemExit) as excinfo:
        validate_input(inputs)
    assert excinfo.value.code == 1


def test_validate_input_tolerates_empty_string_in_required():
    """A required field set to '' must surface as a missing-field error."""
    inputs = _full_inputs(feature_summary="")
    with pytest.raises(SystemExit) as excinfo:
        validate_input(inputs)
    assert excinfo.value.code == 1


def test_validate_input_tolerates_whitespace_only_in_required():
    """A required field of only whitespace/newlines must surface as missing."""
    inputs = _full_inputs(feature_summary="   \n  ")
    with pytest.raises(SystemExit) as excinfo:
        validate_input(inputs)
    assert excinfo.value.code == 1


def test_validate_input_accepts_valid_required_string():
    """A required field with real content must pass validation."""
    inputs = _full_inputs(feature_summary="A real feature idea.")
    # No exception = pass. Return value is the (mutated) inputs dict.
    result = validate_input(inputs)
    assert result["feature_summary"] == "A real feature idea."


# ---------- Encouraged fields: None / empty / whitespace → default message, no crash ----------


def test_validate_input_tolerates_none_value_in_encouraged(capsys):
    """Encouraged field set to None must not crash and must get the 'Not provided.' default."""
    inputs = _full_inputs(internal_context=None)
    result = validate_input(inputs)
    assert result["internal_context"] == "Not provided."
    captured = capsys.readouterr()
    assert "internal_context" in captured.out
    assert "is empty" in captured.out


def test_validate_input_tolerates_empty_string_in_encouraged(capsys):
    """Encouraged field set to '' must get the default without crashing."""
    inputs = _full_inputs(internal_context="")
    result = validate_input(inputs)
    assert result["internal_context"] == "Not provided."


def test_validate_input_tolerates_whitespace_only_in_encouraged(capsys):
    """Encouraged field of only whitespace must get the default without crashing."""
    inputs = _full_inputs(internal_context="   \n  ")
    result = validate_input(inputs)
    assert result["internal_context"] == "Not provided."


def test_validate_input_accepts_valid_encouraged_string():
    """Encouraged field with real content must be preserved."""
    inputs = _full_inputs(internal_context="Real context paragraph.")
    result = validate_input(inputs)
    assert result["internal_context"] == "Real context paragraph."


# ---------- End-to-end smoke: packaged example must pass validation ----------


def test_example_input_brief_passes_validation():
    """The shipped example brief must run through parse_input + validate_input cleanly.

    This is the single most important regression: a fresh checkout of the repo
    must be able to run ``full-pipeline examples/input-brief-example.md`` past
    the validation step. If this test ever fails, the packaged example is
    broken again.
    """
    parsed = parse_input(str(EXAMPLES / "input-brief-example.md"))
    validated = validate_input(parsed)
    # Every required field has real content
    for field in REQUIRED_FIELDS:
        assert validated[field], f"Required field {field} was empty after validation"
    # Every encouraged field is either real content or the default placeholder
    for field in ENCOURAGED_FIELDS:
        assert validated[field], f"Encouraged field {field} still empty after validation"
