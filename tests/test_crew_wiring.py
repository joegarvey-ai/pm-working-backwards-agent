# Feature: internal-mcp-integration
# Property 4: Conditional attachment for BuilderMCPTool
# Property 5: Conditional attachment for OutlookMCPTool
# Unit tests for predicate edge cases and default-off behavior

from __future__ import annotations

import logging
import os
import shutil
import tempfile

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pm_agent_system.crew import (
    PmAgentSystem,
    _builder_mcp_enabled,
    _outlook_mcp_enabled,
)
from pm_agent_system.tools.builder_mcp import BuilderMCPTool
from pm_agent_system.tools.outlook_mcp import OutlookMCPTool


def _tool_class_names(agent) -> list[str]:
    """Return the ``type(tool).__name__`` for every tool attached to an agent."""
    return [type(tool).__name__ for tool in (agent.tools or [])]


# ---------------------------------------------------------------------------
# Strategies for the environment-state Cartesian product
# ---------------------------------------------------------------------------

# BUILDER_MCP_TOKEN / OUTLOOK_MCP_TOKEN states
token_states = st.sampled_from(["unset", "empty", "non-empty"])

# MIDWAY_COOKIE_PATH states
cookie_path_states = st.sampled_from(["unset", "set-and-missing", "set-and-present"])

# Non-empty token value (printable ASCII, realistic for bearer tokens)
token_value_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"), max_codepoint=127
    ),
    min_size=1,
).filter(lambda s: s.strip())


def _setup_env(
    token_env_name: str,
    token_state: str,
    token_value: str,
    cookie_path_state: str,
    tmp_dir: str,
) -> dict[str, str | None]:
    """Configure env vars for one test iteration. Returns originals for restore."""
    cookie_env = "MIDWAY_COOKIE_PATH"
    originals = {
        token_env_name: os.environ.get(token_env_name),
        cookie_env: os.environ.get(cookie_env),
    }

    # --- Token state ---
    if token_state == "unset":
        os.environ.pop(token_env_name, None)
    elif token_state == "empty":
        os.environ[token_env_name] = ""
    elif token_state == "non-empty":
        os.environ[token_env_name] = token_value

    # --- Cookie path state ---
    cookie_file_path = os.path.join(tmp_dir, "midway_cookie")
    missing_file_path = os.path.join(tmp_dir, "nonexistent_cookie")

    if cookie_path_state == "unset":
        os.environ.pop(cookie_env, None)
    elif cookie_path_state == "set-and-missing":
        os.environ[cookie_env] = missing_file_path
    elif cookie_path_state == "set-and-present":
        with open(cookie_file_path, "w", encoding="utf-8") as f:
            f.write("midway-cookie-content")
        os.environ[cookie_env] = cookie_file_path

    return originals


def _restore_env(originals: dict[str, str | None]) -> None:
    """Restore env vars to their original state."""
    for key, value in originals.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


# ---------------------------------------------------------------------------
# Property 4: Conditional attachment for BuilderMCPTool
# For any environment state in the Cartesian product of
# BUILDER_MCP_TOKEN in {unset, empty, non-empty} and
# MIDWAY_COOKIE_PATH in {unset, set-and-missing, set-and-present},
# both external_research_agent.tools and brd_agent.tools contain a
# BuilderMCPTool instance if and only if _builder_mcp_enabled() returns True.
# ---------------------------------------------------------------------------


@given(
    token_state=token_states,
    cookie_path_state=cookie_path_states,
    token_value=token_value_st,
)
@settings(max_examples=30, deadline=None)
def test_property_4_builder_attachment(
    token_state: str,
    cookie_path_state: str,
    token_value: str,
) -> None:
    """**Validates: Requirements 2.1, 2.2, 2.3**

    Property 4: For any environment state in the Cartesian product of
    BUILDER_MCP_TOKEN in {unset, empty, non-empty} and MIDWAY_COOKIE_PATH
    in {unset, set-and-missing, set-and-present}, both
    external_research_agent.tools and brd_agent.tools contain a
    BuilderMCPTool instance if and only if _builder_mcp_enabled() returns
    True for that environment state.
    """
    tmp_dir = tempfile.mkdtemp()
    try:
        originals = _setup_env(
            "BUILDER_MCP_TOKEN", token_state, token_value,
            cookie_path_state, tmp_dir,
        )
        try:
            enabled = _builder_mcp_enabled()
            system = PmAgentSystem()

            ext_research_tools = _tool_class_names(system.external_research_agent())
            brd_tools = _tool_class_names(system.brd_agent())

            if enabled:
                assert "BuilderMCPTool" in ext_research_tools, (
                    f"BuilderMCPTool should be in external_research_agent.tools "
                    f"when _builder_mcp_enabled()=True "
                    f"(token_state={token_state}, cookie={cookie_path_state}), "
                    f"got {ext_research_tools}"
                )
                assert "BuilderMCPTool" in brd_tools, (
                    f"BuilderMCPTool should be in brd_agent.tools "
                    f"when _builder_mcp_enabled()=True "
                    f"(token_state={token_state}, cookie={cookie_path_state}), "
                    f"got {brd_tools}"
                )
            else:
                assert "BuilderMCPTool" not in ext_research_tools, (
                    f"BuilderMCPTool should NOT be in external_research_agent.tools "
                    f"when _builder_mcp_enabled()=False "
                    f"(token_state={token_state}, cookie={cookie_path_state}), "
                    f"got {ext_research_tools}"
                )
                assert "BuilderMCPTool" not in brd_tools, (
                    f"BuilderMCPTool should NOT be in brd_agent.tools "
                    f"when _builder_mcp_enabled()=False "
                    f"(token_state={token_state}, cookie={cookie_path_state}), "
                    f"got {brd_tools}"
                )
        finally:
            _restore_env(originals)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Property 5: Conditional attachment for OutlookMCPTool
# Same shape as Property 4 with OUTLOOK_MCP_TOKEN and _outlook_mcp_enabled()
# substituted; assert presence in prfaq_agent.tools and brd_agent.tools.
# ---------------------------------------------------------------------------


@given(
    token_state=token_states,
    cookie_path_state=cookie_path_states,
    token_value=token_value_st,
)
@settings(max_examples=30, deadline=None)
def test_property_5_outlook_attachment(
    token_state: str,
    cookie_path_state: str,
    token_value: str,
) -> None:
    """**Validates: Requirements 4.1, 4.2, 4.3**

    Property 5: For any environment state in the Cartesian product of
    OUTLOOK_MCP_TOKEN in {unset, empty, non-empty} and MIDWAY_COOKIE_PATH
    in {unset, set-and-missing, set-and-present}, both prfaq_agent.tools
    and brd_agent.tools contain an OutlookMCPTool instance if and only if
    _outlook_mcp_enabled() returns True for that environment state.
    """
    tmp_dir = tempfile.mkdtemp()
    try:
        originals = _setup_env(
            "OUTLOOK_MCP_TOKEN", token_state, token_value,
            cookie_path_state, tmp_dir,
        )
        try:
            enabled = _outlook_mcp_enabled()
            system = PmAgentSystem()

            prfaq_tools = _tool_class_names(system.prfaq_agent())
            brd_tools = _tool_class_names(system.brd_agent())

            if enabled:
                assert "OutlookMCPTool" in prfaq_tools, (
                    f"OutlookMCPTool should be in prfaq_agent.tools "
                    f"when _outlook_mcp_enabled()=True "
                    f"(token_state={token_state}, cookie={cookie_path_state}), "
                    f"got {prfaq_tools}"
                )
                assert "OutlookMCPTool" in brd_tools, (
                    f"OutlookMCPTool should be in brd_agent.tools "
                    f"when _outlook_mcp_enabled()=True "
                    f"(token_state={token_state}, cookie={cookie_path_state}), "
                    f"got {brd_tools}"
                )
            else:
                assert "OutlookMCPTool" not in prfaq_tools, (
                    f"OutlookMCPTool should NOT be in prfaq_agent.tools "
                    f"when _outlook_mcp_enabled()=False "
                    f"(token_state={token_state}, cookie={cookie_path_state}), "
                    f"got {prfaq_tools}"
                )
                assert "OutlookMCPTool" not in brd_tools, (
                    f"OutlookMCPTool should NOT be in brd_agent.tools "
                    f"when _outlook_mcp_enabled()=False "
                    f"(token_state={token_state}, cookie={cookie_path_state}), "
                    f"got {brd_tools}"
                )
        finally:
            _restore_env(originals)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Task 5.8: Unit tests for predicate edge cases and default-off behavior
# ---------------------------------------------------------------------------


def test_external_research_agent_tools_unchanged_when_builder_unset(monkeypatch):
    """Requirement 2.2: external_research_agent.tools length is unchanged
    when BUILDER_MCP_TOKEN and MIDWAY_COOKIE_PATH are both unset.

    The baseline tool set is: TavilySearchTool, CompetitiveIntelTool,
    FileReaderTool, PriorArtSearchTool, ObsidianSearchTool, ObsidianReadTool
    (6 tools total).
    """
    monkeypatch.delenv("BUILDER_MCP_TOKEN", raising=False)
    monkeypatch.delenv("MIDWAY_COOKIE_PATH", raising=False)

    system = PmAgentSystem()
    agent = system.external_research_agent()
    tool_names = _tool_class_names(agent)

    expected_baseline = [
        "TavilySearchTool",
        "CompetitiveIntelTool",
        "FileReaderTool",
        "PriorArtSearchTool",
        "ObsidianSearchTool",
        "ObsidianReadTool",
    ]
    assert len(tool_names) == len(expected_baseline), (
        f"Expected {len(expected_baseline)} tools when builder MCP is disabled, "
        f"got {len(tool_names)}: {tool_names}"
    )
    assert "BuilderMCPTool" not in tool_names


def test_prfaq_agent_tools_original_four_when_outlook_unset(monkeypatch):
    """Requirement 4.3: prfaq_agent.tools contains only the original four
    tools when OUTLOOK_MCP_TOKEN and MIDWAY_COOKIE_PATH are both unset.

    The baseline tool set is: FileReaderTool, StyleGuideLoaderTool,
    ObsidianSearchTool, ObsidianReadTool (4 tools total).
    """
    monkeypatch.delenv("OUTLOOK_MCP_TOKEN", raising=False)
    monkeypatch.delenv("MIDWAY_COOKIE_PATH", raising=False)

    system = PmAgentSystem()
    agent = system.prfaq_agent()
    tool_names = _tool_class_names(agent)

    expected_baseline = [
        "FileReaderTool",
        "StyleGuideLoaderTool",
        "ObsidianSearchTool",
        "ObsidianReadTool",
    ]
    assert tool_names == expected_baseline, (
        f"Expected exactly {expected_baseline} when outlook MCP is disabled, "
        f"got {tool_names}"
    )
    assert "OutlookMCPTool" not in tool_names


def test_startup_log_names_three_integrations(monkeypatch, caplog):
    """Requirement 6.4: the startup log line names the three integrations
    with their enabled/disabled status.
    """
    monkeypatch.delenv("BUILDER_MCP_TOKEN", raising=False)
    monkeypatch.delenv("OUTLOOK_MCP_TOKEN", raising=False)
    monkeypatch.delenv("MIDWAY_COOKIE_PATH", raising=False)
    monkeypatch.delenv("DOVETAIL_API_TOKEN", raising=False)

    with caplog.at_level(logging.INFO, logger="pm_agent_system.crew"):
        PmAgentSystem()

    # Find the integration status log line
    integration_logs = [
        record.message
        for record in caplog.records
        if "builder_mcp" in record.message and "outlook_mcp" in record.message
    ]
    assert len(integration_logs) >= 1, (
        f"Expected at least one log line mentioning builder_mcp and outlook_mcp, "
        f"got log records: {[r.message for r in caplog.records]}"
    )

    log_line = integration_logs[0]
    # All three integrations should be named
    assert "builder_mcp" in log_line
    assert "outlook_mcp" in log_line
    assert "dovetail" in log_line

    # With all tokens unset, all should be disabled
    assert "builder_mcp=disabled" in log_line
    assert "outlook_mcp=disabled" in log_line
    assert "dovetail=disabled" in log_line
