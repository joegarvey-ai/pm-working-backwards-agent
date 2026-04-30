# Feature: internal-mcp-integration, Property 2: BuilderMCPInput args_schema validation
# For any dict containing a non-empty string query and a string action drawn
# from {"wiki_search", "code_search", "taskei_search", "quip_search",
# "pipeline_search"}, optionally extended with string project_id, string
# document_id, and integer limit in [1, 100], Pydantic validation of
# BuilderMCPInput(**d) succeeds. For any dict that omits query, validation
# raises pydantic.ValidationError.
#
# Feature: internal-mcp-integration, Property 8 (Builder half):
# MCP tool _run never raises on error
# For any simulated failure in the HTTP transport, BuilderMCPTool._run(...)
# returns a non-empty string and never propagates the exception.

from __future__ import annotations

import httpx
import pydantic
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from unittest.mock import patch

from pm_agent_system.tools.builder_mcp import BuilderMCPInput, BuilderMCPTool


# ---------------------------------------------------------------------------
# Strategies for Property 2
# ---------------------------------------------------------------------------

VALID_ACTIONS = ["wiki_search", "code_search", "taskei_search", "quip_search", "pipeline_search"]

# Non-empty query strings (at least one character).
query_st = st.text(min_size=1).filter(lambda s: s.strip())

# Valid action from the five-value set.
action_st = st.sampled_from(VALID_ACTIONS)

# Optional string fields (project_id, document_id).
optional_str_st = st.text()

# Limit in [1, 100].
limit_st = st.integers(min_value=1, max_value=100)


@st.composite
def valid_builder_input(draw: st.DrawFn) -> dict:
    """Strategy that produces a dict guaranteed to pass BuilderMCPInput validation."""
    d: dict = {
        "query": draw(query_st),
        "action": draw(action_st),
    }
    # Optionally include project_id, document_id, limit.
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
    d: dict = {
        "action": draw(action_st),
    }
    if draw(st.booleans()):
        d["project_id"] = draw(optional_str_st)
    if draw(st.booleans()):
        d["document_id"] = draw(optional_str_st)
    if draw(st.booleans()):
        d["limit"] = draw(limit_st)
    # Ensure query is NOT present.
    d.pop("query", None)
    return d


# ---------------------------------------------------------------------------
# Property 2: BuilderMCPInput args_schema validation
# ---------------------------------------------------------------------------


@given(data=valid_builder_input())
def test_property_2_builder_input_validation(data: dict) -> None:
    """**Validates: Requirements 1.4**

    Property 2: For any dict containing a non-empty string query and a
    string action drawn from the five-value set, optionally extended with
    string project_id, string document_id, and integer limit in [1, 100],
    Pydantic validation of BuilderMCPInput(**d) succeeds. For any dict
    that omits query, validation raises pydantic.ValidationError.
    """
    # Valid inputs must pass validation.
    model = BuilderMCPInput(**data)
    assert model.query == data["query"]
    assert model.action == data["action"]


@given(data=invalid_builder_input_missing_query())
def test_property_2_builder_input_missing_query_raises(data: dict) -> None:
    """**Validates: Requirements 1.4**

    Property 2 (negative half): For any dict that omits query, Pydantic
    validation raises pydantic.ValidationError.
    """
    with pytest.raises(pydantic.ValidationError):
        BuilderMCPInput(**data)


# ---------------------------------------------------------------------------
# Strategies for Property 8 (Builder half)
# ---------------------------------------------------------------------------

# HTTP status codes for HTTPStatusError simulation.
http_status_codes = st.integers(min_value=400, max_value=599)

# Exception types that _run must handle without raising.
exception_factories = st.sampled_from([
    "http_status_error",
    "timeout_exception",
    "connect_error",
    "generic_exception",
])


def _make_http_status_error(status_code: int) -> httpx.HTTPStatusError:
    """Build a realistic httpx.HTTPStatusError with the given status code."""
    request = httpx.Request("POST", "https://fake-endpoint.example.com/mcp")
    response = httpx.Response(status_code, request=request, text="server error")
    return httpx.HTTPStatusError(
        message=f"HTTP {status_code}",
        request=request,
        response=response,
    )


# ---------------------------------------------------------------------------
# Property 8 (Builder half): _run never raises on transport errors
# ---------------------------------------------------------------------------


@given(
    exc_type=exception_factories,
    status_code=http_status_codes,
    query=st.text(min_size=1),
    action=st.sampled_from(VALID_ACTIONS),
)
@settings(max_examples=100)
def test_property_8_builder_run_never_raises(
    exc_type: str,
    status_code: int,
    query: str,
    action: str,
) -> None:
    """**Validates: Requirements 7.1**

    Property 8 (Builder half): For any simulated failure in the HTTP
    transport (httpx.HTTPStatusError with any status, httpx.TimeoutException,
    httpx.ConnectError, or a generic Exception), BuilderMCPTool._run(...)
    returns a non-empty string and never propagates the exception.
    """
    import os

    # Set required env vars so auth passes and we reach the transport layer.
    orig_token = os.environ.get("BUILDER_MCP_TOKEN")
    orig_endpoint = os.environ.get("BUILDER_MCP_ENDPOINT")
    os.environ["BUILDER_MCP_TOKEN"] = "test-token-value"
    os.environ["BUILDER_MCP_ENDPOINT"] = "https://fake-endpoint.example.com/mcp"

    try:
        # Build the exception to raise.
        if exc_type == "http_status_error":
            exc = _make_http_status_error(status_code)
        elif exc_type == "timeout_exception":
            exc = httpx.TimeoutException("connection timed out")
        elif exc_type == "connect_error":
            exc = httpx.ConnectError("connection refused")
        else:
            exc = Exception("something went wrong")

        tool = BuilderMCPTool()

        with patch("pm_agent_system.tools._mcp_jsonrpc.call_mcp", side_effect=exc):
            result = tool._run(query=query, action=action)

        # _run must return a non-empty string describing the error.
        assert isinstance(result, str)
        assert len(result) > 0
    finally:
        # Restore original env state.
        if orig_token is None:
            os.environ.pop("BUILDER_MCP_TOKEN", None)
        else:
            os.environ["BUILDER_MCP_TOKEN"] = orig_token
        if orig_endpoint is None:
            os.environ.pop("BUILDER_MCP_ENDPOINT", None)
        else:
            os.environ["BUILDER_MCP_ENDPOINT"] = orig_endpoint
