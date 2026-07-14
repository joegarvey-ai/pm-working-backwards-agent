"""Pippin MCP read tool for internal Amazon systems (optional).

Wraps the internal ``python-pippin-mcp`` server (Pippin —
https://pippin.sara.amazon.dev/ — Amazon's canonical PRFAQ/BRD/design-doc
platform). This tool exposes **read** actions only, so the research agent can
pull prior PRFAQs/BRDs and reviewer comments as prior art before drafting.

Writing to Pippin (``create_artifact``) is deliberately NOT here: document
creation is a human-gated action invoked from the CLI (``publish-doc --target
pippin``), never an autonomous agent action. Keeping write out of this tool
preserves the repo's central safety rule (no write capability on any agent).

CONFIRMED CONTRACT against the connected python-pippin-mcp server:
- ``list_projects(max_results?)``
- ``list_artifacts(project_id, max_results?)``
- ``get_artifact(project_id, design_id)``
- ``get_comments(project_id, design_id)``
Remote tool names are env-overridable in case a registry registers them
differently.

Transport mirrors ``builder_mcp``: stdio to an MCP Gateway client binary via
``_mcp_stdio.call_stdio_mcp`` (spawn-per-call, Midway auth handled by the
binary). When the binary is not on PATH, ``_run`` returns a descriptive error
string and never raises, so the OSS pipeline runs unchanged.
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

_CALL_LOG_PATH = Path(os.getenv("OUTPUT_DIR", "./output")) / "pippin_mcp_calls.log"

# MCP Gateway client binary. Overridable; defaults to the AIM registry id.
# Shared default name with the write path's PIPPIN_MCP_BINARY so a single
# override points both at the same client.
_BINARY_NAME = os.getenv("PIPPIN_MCP_BINARY", "python-pippin-mcp").strip() or "python-pippin-mcp"

# Confirmed read tool names (env-overridable).
_LIST_PROJECTS_TOOL = os.getenv("PIPPIN_LIST_PROJECTS_TOOL", "list_projects").strip() or "list_projects"
_LIST_ARTIFACTS_TOOL = os.getenv("PIPPIN_LIST_ARTIFACTS_TOOL", "list_artifacts").strip() or "list_artifacts"
_GET_ARTIFACT_TOOL = os.getenv("PIPPIN_GET_ARTIFACT_TOOL", "get_artifact").strip() or "get_artifact"
_GET_COMMENTS_TOOL = os.getenv("PIPPIN_GET_COMMENTS_TOOL", "get_comments").strip() or "get_comments"


def _list_projects_args(_project: str, _design: str, limit: int) -> dict:
    return {"max_results": limit}


def _list_artifacts_args(project: str, _design: str, limit: int) -> dict:
    return {"project_id": project, "max_results": limit}


def _get_artifact_args(project: str, design: str, _limit: int) -> dict:
    return {"project_id": project, "design_id": design}


def _get_comments_args(project: str, design: str, _limit: int) -> dict:
    return {"project_id": project, "design_id": design}


# Action -> (remote tool name, argument builder, needs_project, needs_design).
_ACTION_MAP: dict[str, tuple[str, callable, bool, bool]] = {
    "list_projects": (_LIST_PROJECTS_TOOL, _list_projects_args, False, False),
    "list_artifacts": (_LIST_ARTIFACTS_TOOL, _list_artifacts_args, True, False),
    "get_artifact": (_GET_ARTIFACT_TOOL, _get_artifact_args, True, True),
    "get_comments": (_GET_COMMENTS_TOOL, _get_comments_args, True, True),
}

_VALID_ACTIONS = ", ".join(f"'{a}'" for a in _ACTION_MAP)


class PippinReadInput(BaseModel):
    """Input schema for PippinReadTool."""

    action: str = Field(
        default="list_projects",
        description=(
            "Read action: 'list_projects' | 'list_artifacts' (needs "
            "'project_id') | 'get_artifact' (needs 'project_id' + 'design_id') "
            "| 'get_comments' (needs 'project_id' + 'design_id')."
        ),
    )
    project_id: str = Field(
        default="",
        description="Pippin project ID. Required for every action except list_projects.",
    )
    design_id: str = Field(
        default="",
        description="Pippin artifact/design ID. Required for get_artifact and get_comments.",
    )
    limit: int = Field(
        default=50,
        description="Max results for list_projects / list_artifacts (1 to 100).",
    )


class PippinReadTool(BaseTool):
    """Read prior PRFAQs/BRDs and reviewer comments from Pippin (read-only).

    Lets the research agent pull prior art (existing artifacts + comments) from
    Amazon's canonical PRFAQ/BRD platform. Requires the ``python-pippin-mcp``
    binary on PATH (override with ``PIPPIN_MCP_BINARY``) and a live Midway
    session; auth is handled by the binary. Absent outside Amazon. This tool is
    read-only — creating Pippin artifacts is a human-gated CLI action, never an
    agent action.
    """

    name: str = "pippin_read"
    description: str = (
        "Read prior art from Pippin (Amazon's canonical PRFAQ/BRD/design-doc "
        "platform), read-only. Actions: 'list_projects', 'list_artifacts' "
        "(needs project_id), 'get_artifact' (needs project_id + design_id), "
        "'get_comments' (needs project_id + design_id). Use it to find and read "
        "prior PRFAQs/BRDs and reviewer comments before drafting. Cannot create "
        "or edit Pippin documents."
    )
    args_schema: Type[BaseModel] = PippinReadInput

    def _run(
        self,
        action: str = "list_projects",
        project_id: str = "",
        design_id: str = "",
        limit: int = 50,
    ) -> str:
        action_clean = (action or "list_projects").strip()
        _mcp_stdio.log_call(
            _CALL_LOG_PATH,
            "invocation",
            {"action": action_clean, "project_id": project_id, "design_id": design_id, "limit": limit},
        )

        mapping = _ACTION_MAP.get(action_clean)
        if mapping is None:
            return f"Unknown action '{action}'. Valid actions: {_VALID_ACTIONS}."

        remote_tool, build_args, needs_project, needs_design = mapping
        if needs_project and not (project_id or "").strip():
            return f"Error: action='{action_clean}' requires a non-empty 'project_id'."
        if needs_design and not (design_id or "").strip():
            return f"Error: action='{action_clean}' requires a non-empty 'design_id'."

        limit = max(1, min(int(limit or 50), 100))
        arguments = build_args(project_id.strip(), design_id.strip(), limit)

        try:
            result = _mcp_stdio.call_stdio_mcp(
                _BINARY_NAME,
                remote_tool,
                arguments,
                timeout=60.0,
            )
            _mcp_stdio.log_call(
                _CALL_LOG_PATH,
                "response",
                {"action": action_clean, "response_chars": len(result), "response_preview": result[:300]},
            )
            return result
        except FileNotFoundError as exc:
            msg = (
                f"{_BINARY_NAME} binary not found on PATH; the Pippin MCP client "
                f"is not installed. Install the MCP Gateway client and run "
                f"'mwinit -f', or set PIPPIN_MCP_BINARY to the installed client "
                f"name. ({exc})"
            )
            _mcp_stdio.log_call(_CALL_LOG_PATH, "binary_missing", {"action": action_clean, "message": str(exc)})
            return msg
        except asyncio.TimeoutError:
            msg = f"Pippin MCP call timed out (action={action_clean})."
            _mcp_stdio.log_call(_CALL_LOG_PATH, "timeout", {"action": action_clean})
            return msg
        except Exception as exc:  # noqa: BLE001 — fail soft like the other read tools
            msg = f"Error connecting to pippin_read: {exc}"
            _mcp_stdio.log_call(
                _CALL_LOG_PATH,
                "exception",
                {"action": action_clean, "type": type(exc).__name__, "message": str(exc)},
            )
            return msg
