"""QuickSight MCP tool for internal Amazon systems (optional).

Wraps the internal ``quicksight-mcp`` server, which reads data from Amazon
QuickSight (Amazon Quick) dashboards and analyses. It is the realistic path to
grounding a BRD's success metrics in real numbers ("how many new developers
registered last month?") rather than the model's assumptions.

CONFIRMED CONTRACT (from the AIM registry documentation): the server exposes a
single tool, ``get_dashboard_data(url, sheet?, visual?, filters?)``, driven as
a three-step flow: (1) discover sheets + parameters, (2) list visuals on a
sheet, (3) export selected visuals. It **returns CSV file paths, not inline
data** — the agent decides whether to read a file. The remote tool name is
env-overridable (``QUICKSIGHT_MCP_TOOL``) in case a registry registers it
differently.

Transport mirrors ``builder_mcp``: stdio to an MCP Gateway client binary via
``_mcp_stdio.call_stdio_mcp`` (spawn-per-call, Midway auth handled by the
binary). When the binary is not on PATH, ``_run`` returns a descriptive error
string and never raises, so the OSS pipeline runs unchanged.

The tool surfaces the raw response (which includes the CSV path + row count on
export) so the agent can decide whether to read the file, rather than inlining
potentially large CSV content. The QuickSight server itself is unverified
against a live host this session (unit-tested, live smoke test pending).
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

_CALL_LOG_PATH = Path(os.getenv("OUTPUT_DIR", "./output")) / "quicksight_mcp_calls.log"

# MCP Gateway client binary. Overridable; defaults to the AIM registry id.
_BINARY_NAME = os.getenv("QUICKSIGHT_MCP_BINARY", "quicksight-mcp").strip() or "quicksight-mcp"

# The single confirmed remote tool. Env-overridable to match the WB-AI idiom.
_REMOTE_TOOL = os.getenv("QUICKSIGHT_MCP_TOOL", "get_dashboard_data").strip() or "get_dashboard_data"

# QuickSight exports can take a while (headless browser + CSV export).
_TIMEOUT = 120.0


class QuickSightInput(BaseModel):
    """Input schema for QuickSightTool (mirrors get_dashboard_data)."""

    url: str = Field(
        ...,
        description=(
            "Full QuickSight dashboard or analysis URL (any region — the region "
            "is extracted from the URL). Required."
        ),
    )
    sheet: str = Field(
        default="",
        description=(
            "Sheet/tab name or ID. Omit to discover the available sheets and "
            "parameters (step 1)."
        ),
    )
    visual: str = Field(
        default="",
        description=(
            "Which visuals to export: 'all' for every visual, or comma-separated "
            "titles. Requires 'sheet'. Omit to list a sheet's visuals (step 2)."
        ),
    )
    filters: str = Field(
        default="",
        description=(
            "Optional comma-separated filter parameters (e.g. 'manager=<alias>' "
            "or 'manager=<alias>,Teams=<team>'). Parameter names come from "
            "step-1 discovery."
        ),
    )


class QuickSightTool(BaseTool):
    """Read data from an Amazon QuickSight dashboard/analysis (read-only).

    Three-step flow: discover sheets/params, list visuals, export visuals as
    CSV. Returns CSV **file paths + row counts**, not inline data — read the
    file only if you need the rows. Requires the ``quicksight-mcp`` binary on
    PATH (override with ``QUICKSIGHT_MCP_BINARY``) and a live Midway session;
    auth is handled by the binary. Absent outside Amazon.
    """

    name: str = "quicksight_dashboard"
    description: str = (
        "Read data from an Amazon QuickSight dashboard or analysis by URL. "
        "Three-step flow: (1) call with just the URL to discover sheets and "
        "filter parameters; (2) add 'sheet' to list its visuals; (3) add "
        "'visual' (a title or 'all') to export CSV. Returns CSV file paths and "
        "row counts, NOT inline data — read a returned file only if you need "
        "the rows. Use it to ground BRD success metrics in real dashboard "
        "numbers."
    )
    args_schema: Type[BaseModel] = QuickSightInput

    def _run(
        self,
        url: str = "",
        sheet: str = "",
        visual: str = "",
        filters: str = "",
    ) -> str:
        _mcp_stdio.log_call(
            _CALL_LOG_PATH,
            "invocation",
            {"url": url, "sheet": sheet, "visual": visual, "filters": filters},
        )

        if not (url or "").strip():
            return "Error: a QuickSight dashboard/analysis 'url' is required."

        # Send only the arguments the caller supplied. Omitting sheet/visual is
        # meaningful (it drives the discover -> list -> export flow), so blanks
        # are not forwarded as empty strings.
        arguments: dict = {"url": url.strip()}
        if sheet.strip():
            arguments["sheet"] = sheet.strip()
        if visual.strip():
            arguments["visual"] = visual.strip()
        if filters.strip():
            arguments["filters"] = filters.strip()

        try:
            result = _mcp_stdio.call_stdio_mcp(
                _BINARY_NAME,
                _REMOTE_TOOL,
                arguments,
                timeout=_TIMEOUT,
            )
            _mcp_stdio.log_call(
                _CALL_LOG_PATH,
                "response",
                {"response_chars": len(result), "response_preview": result[:300]},
            )
            return result
        except FileNotFoundError as exc:
            msg = (
                f"{_BINARY_NAME} binary not found on PATH; the QuickSight MCP "
                f"client is not installed. Install the MCP Gateway client and "
                f"run 'mwinit -o', or set QUICKSIGHT_MCP_BINARY to the installed "
                f"client name. ({exc})"
            )
            _mcp_stdio.log_call(_CALL_LOG_PATH, "binary_missing", {"message": str(exc)})
            return msg
        except asyncio.TimeoutError:
            msg = "QuickSight MCP call timed out (dashboard export can be slow)."
            _mcp_stdio.log_call(_CALL_LOG_PATH, "timeout", {})
            return msg
        except Exception as exc:  # noqa: BLE001 — fail soft like the other read tools
            msg = f"Error connecting to quicksight_dashboard: {exc}"
            _mcp_stdio.log_call(
                _CALL_LOG_PATH,
                "exception",
                {"type": type(exc).__name__, "message": str(exc)},
            )
            return msg
