"""Builder MCP tool for internal Amazon systems.

Wraps the canonical Amazon ``builder-mcp`` server (a stdio MCP binary
distributed by ASBX) and exposes five actions to CrewAI agents:

  wiki_search       Search internal wikis.
  code_search       Search internal code repositories.
  taskei_search     Search Taskei task tracking (optional project_id).
  quip_search       Search Quip documents (optional document_id).
  pipeline_search   Get pipeline details by name.

The action names are stable; tasks.yaml prompts continue to reference
them. Internally each action routes to a canonical builder-mcp tool
(e.g. ``InternalSearch`` with ``domain=WIKI``, ``InternalCodeSearch``,
``TaskeiListTasks``, ``ReadInternalWebsites``, ``GetPipelineDetails``).

Auth is handled by the ``builder-mcp`` binary itself via the user's
Midway cookie (``mwinit -f``). This module does not handle tokens or
endpoint URLs. When the binary is not on PATH, ``_run`` returns a
descriptive error string and never raises, so the OSS variant of the
pipeline runs unchanged for users outside Amazon.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from pm_agent_system.tools import _mcp_stdio

logger = logging.getLogger(__name__)

_CALL_LOG_PATH = Path(os.getenv("OUTPUT_DIR", "./output")) / "builder_mcp_calls.log"

_BINARY_NAME = "builder-mcp"

# ---------------------------------------------------------------------------
# Action -> (canonical tool name, argument-builder) mapping
# ---------------------------------------------------------------------------


# Domains InternalSearch accepts. WIKI is the historical default for
# wiki_search; internal_search can target any of these.
_VALID_DOMAINS = frozenset({
    "ALL", "WIKI", "BUILDER_HUB", "POLICY", "SPYGLASS", "SYSTEM_DESIGN_HUB",
    "SAGE_HORDE", "BROADCAST", "AWS_DOCS", "INSIDE", "PHONETOOL",
})


def _wiki_search_args(query: str, _project: str, _document: str, limit: int, _domain: str) -> dict:
    return {"query": query, "domain": "WIKI", "pageSize": limit}


def _internal_search_args(query: str, _project: str, _document: str, limit: int, domain: str) -> dict:
    # Generic InternalSearch across any supported domain. Defaults to ALL
    # when the caller does not name a valid domain.
    d = (domain or "ALL").strip().upper()
    if d not in _VALID_DOMAINS:
        d = "ALL"
    return {"query": query, "domain": d, "pageSize": limit}


def _code_search_args(query: str, _project: str, _document: str, _limit: int, _domain: str) -> dict:
    # InternalCodeSearch requires searchType; default to code (snippets).
    # The limit parameter is not directly supported; pagination is via
    # the page parameter, which we leave at the default.
    return {"query": query, "searchType": "code"}


def _taskei_search_args(query: str, project: str, _document: str, limit: int, _domain: str) -> dict:
    args: dict = {
        "name": {"queryOperator": "contains", "value": query},
        "pagination": {"maxResults": min(limit, 100)},
    }
    if project:
        args["roomId"] = project
    return args


def _quip_search_args(query: str, _project: str, _document: str, limit: int, _domain: str) -> dict:
    # ReadInternalWebsites does not have a search mode; we pass the
    # quip-amazon.com search URL the user-facing MCP exposes via its
    # URL list. ReadInternalWebsites understands the search route.
    safe_q = query.replace(" ", "+")
    url = f"https://quip-amazon.com/search?query={safe_q}&count={limit}"
    return {"inputs": [url]}


def _pipeline_search_args(query: str, _project: str, _document: str, _limit: int, _domain: str) -> dict:
    # The canonical pipeline tool fetches by name, not free-text search.
    # Treat the query as the pipeline name; the agent prompt already
    # supplies a specific name when this action is used.
    return {"pipelineName": query}


def _acronym_lookup_args(query: str, _project: str, _document: str, _limit: int, _domain: str) -> dict:
    # Resolve an internal Amazon acronym so the synthesis agent does not
    # have to guess what it means.
    return {"acronym": query}


def _golden_path_search_args(query: str, _project: str, _document: str, _limit: int, _domain: str) -> dict:
    # SearchSoftwareRecommendations surfaces blessed/Golden Path tooling
    # for a problem space; the agent then cites the recommendation.
    return {"query": query}


_ACTION_MAP: dict[str, tuple[str, callable]] = {
    "wiki_search": ("InternalSearch", _wiki_search_args),
    "internal_search": ("InternalSearch", _internal_search_args),
    "code_search": ("InternalCodeSearch", _code_search_args),
    "taskei_search": ("TaskeiListTasks", _taskei_search_args),
    "quip_search": ("ReadInternalWebsites", _quip_search_args),
    "pipeline_search": ("GetPipelineDetails", _pipeline_search_args),
    "acronym_lookup": ("SearchAcronymCentral", _acronym_lookup_args),
    "golden_path_search": ("SearchSoftwareRecommendations", _golden_path_search_args),
}

_VALID_ACTIONS = ", ".join(f"'{a}'" for a in _ACTION_MAP)


# ---------------------------------------------------------------------------
# Pydantic args schema
# ---------------------------------------------------------------------------
class BuilderMCPInput(BaseModel):
    """Input schema for BuilderMCPTool."""

    query: str = Field(
        ...,
        description="Free-text query. Required.",
    )
    action: str = Field(
        default="wiki_search",
        description=(
            "Action: 'wiki_search' (Wiki only) | 'internal_search' (any "
            "domain, set 'domain') | 'code_search' | 'taskei_search' | "
            "'quip_search' | 'pipeline_search' | 'acronym_lookup' (resolve "
            "an internal acronym) | 'golden_path_search' (blessed tooling "
            "recommendations for a problem space)."
        ),
    )
    domain: str = Field(
        default="",
        description=(
            "Optional InternalSearch domain for the 'internal_search' action: "
            "ALL, WIKI, BUILDER_HUB, POLICY, SPYGLASS, SYSTEM_DESIGN_HUB, "
            "SAGE_HORDE, BROADCAST, AWS_DOCS, INSIDE, PHONETOOL. Defaults to "
            "ALL. Ignored by other actions."
        ),
    )
    project_id: str = Field(
        default="",
        description=(
            "Optional project identifier for taskei_search or pipeline_search."
        ),
    )
    document_id: str = Field(
        default="",
        description="Optional document identifier for quip_search.",
    )
    limit: int = Field(
        default=10,
        description="Max results (1 to 100).",
    )


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------
class BuilderMCPTool(BaseTool):
    """Search internal Amazon systems via the canonical builder-mcp server.

    Supports: wiki_search, internal_search (any domain), code_search,
    taskei_search, quip_search, pipeline_search, acronym_lookup, and
    golden_path_search. Requires the ``builder-mcp`` binary to be installed
    on PATH (``toolbox install mcp-registry && mcp-registry install
    builder-mcp``) and a valid Midway session (``mwinit -f``). Auth is
    handled by the binary; no env vars are required from this tool.
    """

    name: str = "builder_mcp"
    description: str = (
        "Search internal Amazon systems via the canonical builder-mcp server. "
        "Actions: wiki_search, internal_search (set 'domain'), code_search, "
        "taskei_search, quip_search, pipeline_search, acronym_lookup, "
        "golden_path_search."
    )
    args_schema: Type[BaseModel] = BuilderMCPInput

    # -- public entry point ------------------------------------------------

    def _run(
        self,
        query: str = "",
        action: str = "wiki_search",
        domain: str = "",
        project_id: str = "",
        document_id: str = "",
        limit: int = 10,
    ) -> str:
        _mcp_stdio.log_call(
            _CALL_LOG_PATH,
            "invocation",
            {
                "action": action,
                "query": query,
                "domain": domain,
                "project_id": project_id,
                "document_id": document_id,
                "limit": limit,
            },
        )

        # --- clamp limit --------------------------------------------------
        limit = max(1, min(int(limit or 10), 100))

        # --- dispatch -----------------------------------------------------
        mapping = _ACTION_MAP.get(action)
        if mapping is None:
            return (
                f"Unknown action '{action}'. "
                f"Valid actions: {_VALID_ACTIONS}."
            )
        remote_tool_name, build_args = mapping
        arguments = build_args(query, project_id, document_id, limit, domain)

        # --- call ---------------------------------------------------------
        try:
            result = _mcp_stdio.call_stdio_mcp(
                _BINARY_NAME,
                remote_tool_name,
                arguments,
                timeout=60.0,
            )
            _mcp_stdio.log_call(
                _CALL_LOG_PATH,
                "response",
                {
                    "action": action,
                    "response_chars": len(result),
                    "response_preview": result[:300],
                },
            )
            return result
        except FileNotFoundError as exc:
            msg = (
                f"builder-mcp binary not found on PATH; install via "
                f"'toolbox install mcp-registry && mcp-registry install builder-mcp'. "
                f"({exc})"
            )
            _mcp_stdio.log_call(
                _CALL_LOG_PATH,
                "binary_missing",
                {"action": action, "message": str(exc)},
            )
            return msg
        except asyncio.TimeoutError:
            msg = f"Builder MCP call timed out (action={action})."
            _mcp_stdio.log_call(
                _CALL_LOG_PATH,
                "timeout",
                {"action": action},
            )
            return msg
        except Exception as exc:  # noqa: BLE001
            msg = f"Error connecting to builder_mcp: {exc}"
            _mcp_stdio.log_call(
                _CALL_LOG_PATH,
                "exception",
                {"action": action, "type": type(exc).__name__, "message": str(exc)},
            )
            return msg
