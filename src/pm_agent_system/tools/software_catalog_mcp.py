"""Software Catalog MCP tool for internal Amazon systems (optional).

Wraps the internal ``software-catalog-mcp`` server, which exposes read-only
access to the SoftwareCatalog knowledge graph: Amazon products, services,
features, AWS infrastructure, people/org trees, costs, and zombie services,
plus arbitrary Cypher queries against the underlying Neptune graph. It grounds
the BRD's technical-context section in the real service graph rather than the
model's guesses.

Transport mirrors ``builder_mcp`` / ``working_backwards_ai``: stdio to an MCP
Gateway client binary via ``_mcp_stdio.call_stdio_mcp`` (spawn-per-call, auth
handled by the binary). When the binary is not on PATH, ``_run`` returns a
descriptive error string and never raises, so the OSS pipeline runs unchanged.

⚠️ ASSUMED CONTRACT (unit-tested, live smoke test pending): the
``software-catalog-mcp`` binary would not install on the build host this
session (the AIM registry lists it "In development" and toolbox could not
resolve it), so its exact tool names and arg shapes are UNVERIFIED. The remote
tool names below are best-guess defaults and are env-overridable
(``SOFTWARE_CATALOG_LOOKUP_TOOL``, ``SOFTWARE_CATALOG_CYPHER_TOOL``) so a live
smoke test can correct them without a code change. Only two read actions are
exposed — the minimum a grounding lookup needs — not the full tool surface.
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

_CALL_LOG_PATH = Path(os.getenv("OUTPUT_DIR", "./output")) / "software_catalog_mcp_calls.log"

# MCP Gateway client binary. Overridable for whichever gateway client is
# installed; defaults to the AIM registry id.
_BINARY_NAME = os.getenv("SOFTWARE_CATALOG_MCP_BINARY", "software-catalog-mcp").strip() or "software-catalog-mcp"

# Assumed remote tool names (env-overridable — see module docstring). "lookup"
# resolves a named entity (product/service/feature); "cypher" runs a read-only
# Cypher query for anything the lookup cannot express.
_LOOKUP_TOOL = os.getenv("SOFTWARE_CATALOG_LOOKUP_TOOL", "lookup_entity").strip() or "lookup_entity"
_CYPHER_TOOL = os.getenv("SOFTWARE_CATALOG_CYPHER_TOOL", "run_cypher").strip() or "run_cypher"


def _lookup_args(query: str, _cypher: str, limit: int) -> dict:
    return {"name": query, "limit": limit}


def _cypher_args(_query: str, cypher: str, _limit: int) -> dict:
    return {"query": cypher}


# Action -> (remote tool name, argument builder).
_ACTION_MAP: dict[str, tuple[str, callable]] = {
    "lookup": (_LOOKUP_TOOL, _lookup_args),
    "cypher": (_CYPHER_TOOL, _cypher_args),
}

_VALID_ACTIONS = ", ".join(f"'{a}'" for a in _ACTION_MAP)


class SoftwareCatalogInput(BaseModel):
    """Input schema for SoftwareCatalogTool."""

    query: str = Field(
        default="",
        description=(
            "For action='lookup': the product/service/feature name to resolve "
            "in the SoftwareCatalog knowledge graph. Ignored by action='cypher'."
        ),
    )
    action: str = Field(
        default="lookup",
        description=(
            "Action: 'lookup' (resolve a named product/service/feature and its "
            "attributes) | 'cypher' (run a read-only Cypher query against the "
            "graph; put the query in 'cypher')."
        ),
    )
    cypher: str = Field(
        default="",
        description="For action='cypher': the read-only Cypher query to run.",
    )
    limit: int = Field(
        default=10,
        description="Max results for 'lookup' (1 to 50).",
    )


class SoftwareCatalogTool(BaseTool):
    """Query the internal Amazon SoftwareCatalog knowledge graph (read-only).

    Grounds BRD technical context in the real product/service/feature graph.
    Requires the ``software-catalog-mcp`` binary on PATH (override with
    ``SOFTWARE_CATALOG_MCP_BINARY``) and a live Midway session; auth is handled
    by the binary. Absent outside Amazon, so it stays unregistered there.
    """

    name: str = "software_catalog"
    description: str = (
        "Query the internal Amazon SoftwareCatalog knowledge graph (read-only): "
        "products, services, features, AWS infrastructure, org trees, and costs. "
        "Actions: 'lookup' (resolve a named entity) or 'cypher' (read-only graph "
        "query). Use it to ground the BRD's technical context in real internal "
        "services rather than assumptions."
    )
    args_schema: Type[BaseModel] = SoftwareCatalogInput

    def _run(
        self,
        query: str = "",
        action: str = "lookup",
        cypher: str = "",
        limit: int = 10,
    ) -> str:
        action_clean = (action or "lookup").strip().lower()
        _mcp_stdio.log_call(
            _CALL_LOG_PATH,
            "invocation",
            {"action": action_clean, "query": query, "cypher_chars": len(cypher or ""), "limit": limit},
        )

        mapping = _ACTION_MAP.get(action_clean)
        if mapping is None:
            return f"Unknown action '{action}'. Valid actions: {_VALID_ACTIONS}."

        # Per-action required inputs.
        if action_clean == "lookup" and not (query or "").strip():
            return "Error: action='lookup' requires a non-empty 'query' (entity name)."
        if action_clean == "cypher" and not (cypher or "").strip():
            return "Error: action='cypher' requires a non-empty 'cypher' query."

        limit = max(1, min(int(limit or 10), 50))
        remote_tool, build_args = mapping
        arguments = build_args(query, cypher, limit)

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
                f"{_BINARY_NAME} binary not found on PATH; the Software Catalog "
                f"MCP client is not installed. Install the MCP Gateway client "
                f"and run 'mwinit -f', or set SOFTWARE_CATALOG_MCP_BINARY to the "
                f"installed client name. ({exc})"
            )
            _mcp_stdio.log_call(_CALL_LOG_PATH, "binary_missing", {"action": action_clean, "message": str(exc)})
            return msg
        except asyncio.TimeoutError:
            msg = f"Software Catalog MCP call timed out (action={action_clean})."
            _mcp_stdio.log_call(_CALL_LOG_PATH, "timeout", {"action": action_clean})
            return msg
        except Exception as exc:  # noqa: BLE001 — fail soft like the other read tools
            msg = f"Error connecting to software_catalog: {exc}"
            _mcp_stdio.log_call(
                _CALL_LOG_PATH,
                "exception",
                {"action": action_clean, "type": type(exc).__name__, "message": str(exc)},
            )
            return msg
