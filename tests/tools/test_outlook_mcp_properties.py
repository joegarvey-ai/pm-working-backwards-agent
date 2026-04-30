# Feature: internal-mcp-integration, Property 3: OutlookMCPInput args_schema validation
# For any dict containing a non-empty string query and a string action drawn
# from {"calendar_search", "email_search", "room_availability",
# "schedule_summary"}, optionally extended with ISO-8601 start_date,
# end_date, comma-separated participants, and integer limit in [1, 100],
# Pydantic validation of OutlookMCPInput(**d) succeeds. For any dict that
# omits query, validation raises pydantic.ValidationError.
#
# Feature: internal-mcp-integration, Property 6: Email body scrubbing
# For any JSON-serializable input structure (nested dicts and lists of
# arbitrary depth) in which any subset of the keys body, body_preview,
# and body_html may appear at any depth, the serialized output of
# _scrub_email_bodies(input) does not contain those keys at any depth.
# Preserved fields (subject, from, date, to, cc, summary) round-trip
# unchanged.
#
# Feature: internal-mcp-integration, Property 8 (Outlook half):
# MCP tool _run never raises on error
# For any simulated failure in the HTTP transport, OutlookMCPTool._run(...)
# returns a non-empty string and never propagates the exception.

from __future__ import annotations

import json
import os
from unittest.mock import patch

import httpx
import pydantic
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pm_agent_system.tools.outlook_mcp import (
    OutlookMCPInput,
    OutlookMCPTool,
    _scrub_email_bodies,
)


# ---------------------------------------------------------------------------
# Strategies for Property 3
# ---------------------------------------------------------------------------

VALID_ACTIONS = [
    "calendar_search",
    "email_search",
    "room_availability",
    "schedule_summary",
]

# Non-empty query strings (at least one printable character).
query_st = st.text(min_size=1).filter(lambda s: s.strip())

# Valid action from the four-value set.
action_st = st.sampled_from(VALID_ACTIONS)

# ISO-8601 date strings (simplified: YYYY-MM-DD format).
iso_date_st = st.dates().map(lambda d: d.isoformat())

# Comma-separated participant aliases.
participant_st = st.lists(
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "Nd"), whitelist_characters="@._-"),
        min_size=1,
        max_size=30,
    ),
    min_size=0,
    max_size=5,
).map(lambda parts: ",".join(parts))

# Limit in [1, 100].
limit_st = st.integers(min_value=1, max_value=100)


@st.composite
def valid_outlook_input(draw: st.DrawFn) -> dict:
    """Strategy that produces a dict guaranteed to pass OutlookMCPInput validation."""
    d: dict = {
        "query": draw(query_st),
        "action": draw(action_st),
    }
    if draw(st.booleans()):
        d["start_date"] = draw(iso_date_st)
    if draw(st.booleans()):
        d["end_date"] = draw(iso_date_st)
    if draw(st.booleans()):
        d["participants"] = draw(participant_st)
    if draw(st.booleans()):
        d["limit"] = draw(limit_st)
    return d


@st.composite
def invalid_outlook_input_missing_query(draw: st.DrawFn) -> dict:
    """Strategy that produces a dict missing the required 'query' field."""
    d: dict = {
        "action": draw(action_st),
    }
    if draw(st.booleans()):
        d["start_date"] = draw(iso_date_st)
    if draw(st.booleans()):
        d["end_date"] = draw(iso_date_st)
    if draw(st.booleans()):
        d["participants"] = draw(participant_st)
    if draw(st.booleans()):
        d["limit"] = draw(limit_st)
    # Ensure query is NOT present.
    d.pop("query", None)
    return d


# ---------------------------------------------------------------------------
# Property 3: OutlookMCPInput args_schema validation
# ---------------------------------------------------------------------------


@given(data=valid_outlook_input())
def test_property_3_outlook_input_validation(data: dict) -> None:
    """**Validates: Requirements 3.4**

    Property 3: For any dict containing a non-empty string query and a
    string action drawn from the four-value set, optionally extended with
    ISO-8601 dates, comma-separated participants, and integer limit in
    [1, 100], Pydantic validation of OutlookMCPInput(**d) succeeds.
    """
    model = OutlookMCPInput(**data)
    assert model.query == data["query"]
    assert model.action == data["action"]


@given(data=invalid_outlook_input_missing_query())
def test_property_3_outlook_input_missing_query_raises(data: dict) -> None:
    """**Validates: Requirements 3.4**

    Property 3 (negative half): For any dict that omits query, Pydantic
    validation raises pydantic.ValidationError.
    """
    with pytest.raises(pydantic.ValidationError):
        OutlookMCPInput(**data)


# ---------------------------------------------------------------------------
# Strategies for Property 6: email body scrubbing
# ---------------------------------------------------------------------------

# Keys that must be scrubbed.
SCRUB_KEYS = ["body", "body_preview", "body_html"]

# Keys that must be preserved.
PRESERVED_KEYS = ["subject", "from", "date", "to", "cc", "summary"]

# Strategy for leaf values (strings, ints, bools, None).
leaf_values = st.one_of(
    st.text(max_size=50),
    st.integers(min_value=-1000, max_value=1000),
    st.booleans(),
    st.none(),
)


def _nested_json(max_depth: int = 3) -> st.SearchStrategy:
    """Strategy for arbitrary nested JSON structures with scrub keys injected."""
    if max_depth <= 0:
        return leaf_values

    child = st.deferred(lambda: _nested_json(max_depth - 1))

    dict_st = st.dictionaries(
        keys=st.one_of(
            st.sampled_from(SCRUB_KEYS + PRESERVED_KEYS),
            st.text(min_size=1, max_size=10),
        ),
        values=child,
        min_size=0,
        max_size=5,
    )
    list_st = st.lists(child, min_size=0, max_size=5)

    return st.one_of(leaf_values, dict_st, list_st)


def _contains_scrub_keys(node) -> bool:
    """Return True if any scrub key appears at any depth in *node*."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in SCRUB_KEYS:
                return True
            if _contains_scrub_keys(value):
                return True
    elif isinstance(node, list):
        for item in node:
            if _contains_scrub_keys(item):
                return True
    return False


# ---------------------------------------------------------------------------
# Property 6: Email body scrubbing
# ---------------------------------------------------------------------------


@given(data=_nested_json(max_depth=3))
@settings(max_examples=200)
def test_property_6_email_body_scrubbing(data) -> None:
    """**Validates: Requirements 3.6**

    Property 6: For any JSON-serializable input structure with any subset
    of body, body_preview, body_html keys at any depth, the output of
    _scrub_email_bodies does not contain those keys at any depth.
    Preserved keys (subject, from, date, to, cc, summary) round-trip
    unchanged.
    """
    # Only test dict/list inputs (the scrubber returns an error for non-JSON).
    if not isinstance(data, (dict, list)):
        return

    raw_text = json.dumps(data)
    result_text = _scrub_email_bodies(raw_text)
    result = json.loads(result_text)

    # Assert no scrub keys remain at any depth.
    assert not _contains_scrub_keys(result), (
        f"Scrub keys found in output: {result}"
    )

    # Assert preserved keys round-trip unchanged.
    _assert_preserved_keys_unchanged(data, result)


def _assert_preserved_keys_unchanged(original, scrubbed) -> None:
    """Walk original and scrubbed in parallel, asserting preserved values match."""
    if isinstance(original, dict) and isinstance(scrubbed, dict):
        for key in PRESERVED_KEYS:
            if key in original and key in scrubbed:
                orig_val = original[key]
                scrub_val = scrubbed[key]
                # Only compare simple values; nested structures may have
                # been recursively scrubbed (which is correct behavior).
                if not isinstance(orig_val, (dict, list)):
                    assert scrub_val == orig_val, (
                        f"Preserved key '{key}' changed: {orig_val!r} -> {scrub_val!r}"
                    )
                else:
                    # Recurse into nested structures
                    _assert_preserved_keys_unchanged(orig_val, scrub_val)
        # Recurse into all shared keys
        for key in original:
            if key in scrubbed and key not in SCRUB_KEYS:
                _assert_preserved_keys_unchanged(original[key], scrubbed[key])
    elif isinstance(original, list) and isinstance(scrubbed, list):
        for orig_item, scrub_item in zip(original, scrubbed):
            _assert_preserved_keys_unchanged(orig_item, scrub_item)


# ---------------------------------------------------------------------------
# Strategies for Property 8 (Outlook half)
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
# Property 8 (Outlook half): _run never raises on transport errors
# ---------------------------------------------------------------------------


@given(
    exc_type=exception_factories,
    status_code=http_status_codes,
    query=st.text(min_size=1),
    action=st.sampled_from(VALID_ACTIONS),
)
@settings(max_examples=100)
def test_property_8_outlook_run_never_raises(
    exc_type: str,
    status_code: int,
    query: str,
    action: str,
) -> None:
    """**Validates: Requirements 7.2**

    Property 8 (Outlook half): For any simulated failure in the HTTP
    transport (httpx.HTTPStatusError with any status, httpx.TimeoutException,
    httpx.ConnectError, or a generic Exception), OutlookMCPTool._run(...)
    returns a non-empty string and never propagates the exception.
    """
    # Set required env vars so auth passes and we reach the transport layer.
    orig_token = os.environ.get("OUTLOOK_MCP_TOKEN")
    orig_endpoint = os.environ.get("OUTLOOK_MCP_ENDPOINT")
    os.environ["OUTLOOK_MCP_TOKEN"] = "test-token-value"
    os.environ["OUTLOOK_MCP_ENDPOINT"] = "https://fake-endpoint.example.com/mcp"

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

        tool = OutlookMCPTool()

        with patch("pm_agent_system.tools._mcp_jsonrpc.call_mcp", side_effect=exc):
            result = tool._run(query=query, action=action)

        # _run must return a non-empty string describing the error.
        assert isinstance(result, str)
        assert len(result) > 0
    finally:
        # Restore original env state.
        if orig_token is None:
            os.environ.pop("OUTLOOK_MCP_TOKEN", None)
        else:
            os.environ["OUTLOOK_MCP_TOKEN"] = orig_token
        if orig_endpoint is None:
            os.environ.pop("OUTLOOK_MCP_ENDPOINT", None)
        else:
            os.environ["OUTLOOK_MCP_ENDPOINT"] = orig_endpoint
