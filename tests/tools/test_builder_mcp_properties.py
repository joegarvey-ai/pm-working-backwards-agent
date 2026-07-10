# Property tests for BuilderMCPTool.
#
# Property 2: BuilderMCPInput args_schema validation.
#   For any dict containing a non-empty string query and a string action
#   drawn from the five-value action set, optionally extended with
#   string project_id, string document_id, and integer limit in [1, 100],
#   Pydantic validation of BuilderMCPInput(**d) succeeds. For any dict
#   that omits query, validation raises pydantic.ValidationError.
#
# Property 8 (Builder half): _run never raises on transport errors.
#   For any simulated failure in the stdio MCP call (FileNotFoundError,
#   asyncio.TimeoutError, or a generic Exception), BuilderMCPTool._run(...)
#   returns a non-empty string and never propagates the exception.

from __future__ import annotations

import asyncio
import pydantic
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from unittest.mock import patch

from pm_agent_system.tools.builder_mcp import BuilderMCPInput, BuilderMCPTool


# ---------------------------------------------------------------------------
# Strategies for Property 2
# ---------------------------------------------------------------------------

VALID_ACTIONS = [
    "wiki_search",
    "internal_search",
    "code_search",
    "taskei_search",
    "quip_search",
    "pipeline_search",
    "acronym_lookup",
    "golden_path_search",
]

query_st = st.text(min_size=1).filter(lambda s: s.strip())
action_st = st.sampled_from(VALID_ACTIONS)
optional_str_st = st.text()
limit_st = st.integers(min_value=1, max_value=100)


@st.composite
def valid_builder_input(draw: st.DrawFn) -> dict:
    """Strategy that produces a dict guaranteed to pass BuilderMCPInput validation."""
    d: dict = {
        "query": draw(query_st),
        "action": draw(action_st),
    }
    if draw(st.booleans()):
        d["project_id"] = draw(optional_str_st)
    if draw(st.booleans()):
        d["document_id"] = draw(optional_str_st)
    if draw(st.booleans()):
        d["limit"] = draw(limit_st)
    return d


@st.composite
def invalid_builder_input_missing_query(draw: st.DrawFn) -> dict:
    """Strategy that produces a dict missing the required 'query' field."""
    d: dict = {"action": draw(action_st)}
    if draw(st.booleans()):
        d["project_id"] = draw(optional_str_st)
    if draw(st.booleans()):
        d["document_id"] = draw(optional_str_st)
    if draw(st.booleans()):
        d["limit"] = draw(limit_st)
    d.pop("query", None)
    return d


# ---------------------------------------------------------------------------
# Property 2
# ---------------------------------------------------------------------------


@given(data=valid_builder_input())
def test_property_2_builder_input_validation(data: dict) -> None:
    model = BuilderMCPInput(**data)
    assert model.query == data["query"]
    assert model.action == data["action"]


@given(data=invalid_builder_input_missing_query())
def test_property_2_builder_input_missing_query_raises(data: dict) -> None:
    with pytest.raises(pydantic.ValidationError):
        BuilderMCPInput(**data)


# ---------------------------------------------------------------------------
# Property 8 (Builder half): _run never raises on transport errors
# ---------------------------------------------------------------------------


exception_factories = st.sampled_from([
    "binary_missing",
    "timeout",
    "generic",
])


@given(
    exc_type=exception_factories,
    query=st.text(min_size=1),
    action=st.sampled_from(VALID_ACTIONS),
)
@settings(max_examples=100)
def test_property_8_builder_run_never_raises(
    exc_type: str,
    query: str,
    action: str,
) -> None:
    """_run returns a non-empty string for any simulated transport failure."""
    if exc_type == "binary_missing":
        exc = FileNotFoundError("'builder-mcp' is not on PATH")
        binary_present = False
    elif exc_type == "timeout":
        exc = asyncio.TimeoutError()
        binary_present = True
    else:
        exc = Exception("something went wrong")
        binary_present = True

    tool = BuilderMCPTool()

    with patch(
        "pm_agent_system.tools._mcp_stdio.is_binary_available",
        return_value=binary_present,
    ), patch(
        "pm_agent_system.tools.builder_mcp._mcp_stdio.call_stdio_mcp",
        side_effect=exc,
    ):
        result = tool._run(query=query, action=action)

    assert isinstance(result, str)
    assert len(result) > 0
