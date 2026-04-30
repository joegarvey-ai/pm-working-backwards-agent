"""Builder MCP tool for internal Amazon systems.

Wraps builder-mcp's JSON-RPC endpoint and exposes five actions:
  wiki_search       Search internal wikis.
  code_search       Search internal code repositories.
  taskei_search     Search Taskei task tracking (optional project_id).
  quip_search       Search Quip documents (optional document_id).
  pipeline_search   Search pipelines (optional project_id).

Authentication resolves via the shared ``_mcp_jsonrpc`` helper: midway
cookie first, ``BUILDER_MCP_TOKEN`` fallback. When neither is available,
``_run`` returns a descriptive error string and never raises.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Type

import httpx
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from pm_agent_system.tools import _mcp_jsonrpc

logger = logging.getLogger(__name__)

_CALL_LOG_PATH = Path(os.getenv("OUTPUT_DIR", "./output")) / "builder_mcp_calls.log"

# ---------------------------------------------------------------------------
# Action to remote MCP tool name mapping
# ---------------------------------------------------------------------------
_ACTION_MAP: dict[str, str] = {
    "wiki_search": "search_wiki",
    "code_search": "search_code",
    "taskei_search": "search_taskei",
    "quip_search": "search_quip",
    "pipeline_search": "search_pipelines",
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
            "Action: 'wiki_search' | 'code_search' | 'taskei_search' | "
            "'quip_search' | 'pipeline_search'."
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
    """Search internal Amazon systems via builder-mcp.

    Supports five actions: wiki_search, code_search, taskei_search,
    quip_search, and pipeline_search. Requires BUILDER_MCP_TOKEN (or
    MIDWAY_COOKIE_PATH) and BUILDER_MCP_ENDPOINT to be set.
    """

    name: str = "builder_mcp"
    description: str = (
        "Search internal Amazon systems via builder-mcp. "
        "Actions: wiki_search, code_search, taskei_search, "
        "quip_search, pipeline_search."
    )
    args_schema: Type[BaseModel] = BuilderMCPInput

    # -- public entry point ------------------------------------------------

    def _run(
        self,
        query: str = "",
        action: str = "wiki_search",
        project_id: str = "",
        document_id: str = "",
        limit: int = 10,
    ) -> str:
        _mcp_jsonrpc.log_call(
            _CALL_LOG_PATH,
            "invocation",
            {
                "action": action,
                "query": query,
                "project_id": project_id,
                "document_id": document_id,
                "limit": limit,
            },
        )

        # --- auth ---------------------------------------------------------
        auth = _mcp_jsonrpc.resolve_auth(
            "MIDWAY_COOKIE_PATH", "BUILDER_MCP_TOKEN", logger
        )
        if auth.bearer_token is None and auth.cookie_header is None:
            msg = (
                "BUILDER_MCP_TOKEN not set in environment variables; "
                "set token or MIDWAY_COOKIE_PATH to enable builder_mcp."
            )
            _mcp_jsonrpc.log_call(_CALL_LOG_PATH, "auth_error", {"message": msg})
            return msg

        # --- endpoint -----------------------------------------------------
        endpoint = os.getenv("BUILDER_MCP_ENDPOINT", "").strip()
        if not endpoint:
            msg = (
                "BUILDER_MCP_ENDPOINT not set in environment variables; "
                "set it to the builder-mcp JSON-RPC endpoint URL."
            )
            _mcp_jsonrpc.log_call(_CALL_LOG_PATH, "config_error", {"message": msg})
            return msg

        # --- clamp limit --------------------------------------------------
        limit = max(1, min(int(limit or 10), 100))

        # --- dispatch and call --------------------------------------------
        try:
            remote_tool_name, args = self._dispatch(
                action, query, project_id, document_id, limit
            )
        except ValueError as exc:
            # Unknown action
            return str(exc)

        try:
            result = _mcp_jsonrpc.call_mcp(
                endpoint, auth, remote_tool_name, args, timeout=30.0
            )
            _mcp_jsonrpc.log_call(
                _CALL_LOG_PATH,
                "response",
                {
                    "action": action,
                    "response_chars": len(result),
                    "response_preview": result[:300],
                },
            )
            return result
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300] if exc.response else ""
            status = exc.response.status_code if exc.response else "unknown"
            msg = f"Builder MCP error (HTTP {status}): {body}"
            _mcp_jsonrpc.log_call(
                _CALL_LOG_PATH,
                "http_error",
                {"action": action, "status": status, "body": body},
            )
            return msg
        except Exception as exc:  # noqa: BLE001
            msg = f"Error connecting to builder_mcp: {exc}"
            _mcp_jsonrpc.log_call(
                _CALL_LOG_PATH,
                "exception",
                {"action": action, "type": type(exc).__name__, "message": str(exc)},
            )
            return msg

    # -- dispatch ----------------------------------------------------------

    @staticmethod
    def _dispatch(
        action: str,
        query: str,
        project_id: str,
        document_id: str,
        limit: int,
    ) -> tuple[str, dict]:
        """Map *action* to the remote MCP tool name and build the args dict.

        Returns ``(remote_tool_name, arguments)`` on success.
        Raises ``ValueError`` for unknown actions.
        """
        remote_tool = _ACTION_MAP.get(action)
        if remote_tool is None:
            raise ValueError(
                f"Unknown action '{action}'. "
                f"Valid actions: {_VALID_ACTIONS}."
            )

        # Base arguments shared by every action
        args: dict = {"query": query, "limit": limit}

        # Attach optional identifiers per the action mapping table
        if action == "taskei_search" and project_id:
            args["project_id"] = project_id
        elif action == "quip_search" and document_id:
            args["document_id"] = document_id
        elif action == "pipeline_search" and project_id:
            args["project_id"] = project_id

        return remote_tool, args
