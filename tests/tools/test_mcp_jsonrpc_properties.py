# Feature: internal-mcp-integration, Property 1: JSON-RPC envelope structural invariants
# For any string tool_name and any JSON-serializable dict arguments,
# the output of jsonrpc_envelope(tool_name, arguments) satisfies:
#   - envelope["jsonrpc"] == "2.0"
#   - envelope["method"] == "tools/call"
#   - envelope["params"] == {"name": tool_name, "arguments": arguments}
#   - json.loads(json.dumps(envelope)) == envelope
#   - Top-level keys are exactly {"jsonrpc", "method", "params", "id"}

from __future__ import annotations

import json
import logging
import logging.handlers

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pm_agent_system.tools._mcp_jsonrpc import MCPAuth, jsonrpc_envelope, resolve_auth

# Strategy for JSON-serializable values: text, integers, finite floats,
# booleans, and None as base cases, composed recursively into lists and dicts.
json_values = st.recursive(
    st.text() | st.integers() | st.floats(allow_nan=False) | st.booleans() | st.none(),
    lambda children: st.lists(children) | st.dictionaries(st.text(), children),
    max_leaves=15,
)

# Strategy for the arguments dict passed to jsonrpc_envelope.
json_dicts = st.dictionaries(st.text(), json_values)


@given(tool_name=st.text(), arguments=json_dicts)
def test_property_1_envelope_invariants(tool_name: str, arguments: dict) -> None:
    """**Validates: Requirements 1.3, 3.3**

    Property 1: For any string tool_name and any JSON-serializable dict
    arguments, the output of jsonrpc_envelope(tool_name, arguments) satisfies
    all five structural invariants defined in the design document.
    """
    envelope = jsonrpc_envelope(tool_name, arguments)

    # 1. jsonrpc version is "2.0"
    assert envelope["jsonrpc"] == "2.0"

    # 2. method is "tools/call"
    assert envelope["method"] == "tools/call"

    # 3. params nests the caller's tool_name and arguments verbatim
    assert envelope["params"] == {"name": tool_name, "arguments": arguments}

    # 4. The envelope round-trips through JSON serialization
    assert json.loads(json.dumps(envelope)) == envelope

    # 5. Top-level keys are exactly the expected set
    assert set(envelope.keys()) == {"jsonrpc", "method", "params", "id"}


# ---------------------------------------------------------------------------
# Feature: internal-mcp-integration, Property 7: Auth resolver precedence
# For any combination of cookie_path_state in {unset, set-and-missing,
# set-and-present-with-content} and token_state in {unset, empty, non-empty},
# the return value of resolve_auth(cookie_env, token_env, logger) satisfies:
#   - When the cookie path is set and the file exists with content:
#     result.cookie_header is non-None and result.bearer_token is None
#   - Otherwise when the token is non-empty:
#     result.bearer_token is non-None and result.cookie_header is None
#   - Otherwise both fields are None
#   - When the cookie path is set but the file is missing:
#     a warning-level log record is emitted before fallback
# ---------------------------------------------------------------------------

# Strategies for the two state dimensions.
cookie_path_states = st.sampled_from(["unset", "set-and-missing", "set-and-present-with-content"])
token_states = st.sampled_from(["unset", "empty", "non-empty"])

# Non-empty cookie content: printable ASCII (realistic for cookie values).
cookie_content_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S"), max_codepoint=127),
    min_size=1,
).filter(lambda s: s.strip())

# Non-empty token: printable ASCII (realistic for bearer tokens).
token_value_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S"), max_codepoint=127),
    min_size=1,
).filter(lambda s: s.strip())


@given(
    cookie_state=cookie_path_states,
    token_state=token_states,
    cookie_content=cookie_content_st,
    token_value=token_value_st,
)
@settings(max_examples=200)
def test_property_7_auth_resolver_precedence(
    cookie_state: str,
    token_state: str,
    cookie_content: str,
    token_value: str,
) -> None:
    """**Validates: Requirements 5.2, 5.3, 5.4, 5.5**

    Property 7: For any combination of cookie_path_state and token_state,
    resolve_auth returns the correct MCPAuth and emits warnings when the
    cookie path is set but the file is missing.
    """
    import os
    import tempfile

    cookie_env = "TEST_PROP7_COOKIE_PATH"
    token_env = "TEST_PROP7_TOKEN"

    # Save original env state for cleanup.
    orig_cookie = os.environ.get(cookie_env)
    orig_token = os.environ.get(token_env)

    tmp_dir = tempfile.mkdtemp()
    cookie_file_path = os.path.join(tmp_dir, "cookie_file")
    missing_file_path = os.path.join(tmp_dir, "nonexistent_cookie_file")

    try:
        # --- Set up cookie_path_state ---
        if cookie_state == "unset":
            os.environ.pop(cookie_env, None)
        elif cookie_state == "set-and-missing":
            os.environ[cookie_env] = missing_file_path
        elif cookie_state == "set-and-present-with-content":
            with open(cookie_file_path, "w", encoding="utf-8") as f:
                f.write(cookie_content)
            os.environ[cookie_env] = cookie_file_path

        # --- Set up token_state ---
        if token_state == "unset":
            os.environ.pop(token_env, None)
        elif token_state == "empty":
            os.environ[token_env] = ""
        elif token_state == "non-empty":
            os.environ[token_env] = token_value

        # --- Call resolve_auth with a capturing log handler ---
        test_logger = logging.getLogger("test_property_7")
        test_logger.setLevel(logging.DEBUG)
        handler = logging.handlers.MemoryHandler(capacity=1000)
        handler.setLevel(logging.WARNING)
        test_logger.addHandler(handler)

        try:
            result = resolve_auth(cookie_env, token_env, test_logger)
        finally:
            test_logger.removeHandler(handler)

        # --- Assertions based on precedence rules ---
        assert isinstance(result, MCPAuth)

        if cookie_state == "set-and-present-with-content":
            # Cookie wins: cookie_header is set, bearer_token is None.
            assert result.cookie_header is not None
            assert result.cookie_header == cookie_content.strip()
            assert result.bearer_token is None
        elif token_state == "non-empty":
            # Token fallback: bearer_token is set, cookie_header is None.
            assert result.bearer_token is not None
            assert result.bearer_token == token_value.strip()
            assert result.cookie_header is None
        else:
            # No auth material available.
            assert result.bearer_token is None
            assert result.cookie_header is None

        # --- Warning assertion for set-and-missing cookie path ---
        if cookie_state == "set-and-missing":
            warning_records = [
                r for r in handler.buffer
                if r.levelno >= logging.WARNING
            ]
            assert len(warning_records) > 0, (
                "Expected a warning log when cookie path is set but file is missing"
            )

    finally:
        # Restore original env state.
        if orig_cookie is None:
            os.environ.pop(cookie_env, None)
        else:
            os.environ[cookie_env] = orig_cookie
        if orig_token is None:
            os.environ.pop(token_env, None)
        else:
            os.environ[token_env] = orig_token

        # Clean up temp files.
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
