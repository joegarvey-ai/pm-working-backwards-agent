"""Working Backwards AI critique tool (optional, internal Amazon).

Composes the pipeline's PRFAQ stage with the canonical internal
`Working Backwards AI` service (workingbackwards.amazon.dev), which
pressure-tests a Working Backwards document through simulated customer
personas and domain-expert reviewers (including Senior Leader and
Responsible AI). It reached MCP availability in 2026, so an external
agent can invoke it rather than re-implementing persona critique locally.

Design notes:
- Transport is stdio via the MCP Gateway client binary, mirroring
  ``builder_mcp`` (spawn-per-call, Midway auth handled by the binary).
  The binary name is overridable via ``WB_AI_MCP_BINARY`` for whichever
  MCP Gateway client is installed; it defaults to ``wb-ai-mcp``.
- Transparent relay: Working Backwards AI owns its own coaching logic, so
  this tool forwards the PM's draft text verbatim and returns the
  service's critique verbatim. It does not paraphrase, pre-filter, or
  interpret the exchange.
- Single-shot: Working Backwards AI is a stateful multi-turn coach, but
  this pipeline is a batch artifact generator with human checkpoints, so
  the tool issues one critique request per call. Multi-turn refinement
  stays a human activity in the WB AI web app.
- Fail-soft: when the binary is not on PATH, ``_run`` returns a
  descriptive error string and never raises, so the OSS pipeline runs
  unchanged outside Amazon.

This tool is optional and is only attached to the PRFAQ agent when the
MCP binary is present (see ``crew.py`` ``_wb_ai_enabled``).
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

_CALL_LOG_PATH = Path(os.getenv("OUTPUT_DIR", "./output")) / "wb_ai_mcp_calls.log"

# MCP Gateway client binary that exposes the Working Backwards AI server.
# Overridable because the installed gateway client name can vary.
_BINARY_NAME = os.getenv("WB_AI_MCP_BINARY", "wb-ai-mcp").strip() or "wb-ai-mcp"

# Canonical remote tool the Working Backwards AI MCP server exposes for a
# single agent-to-agent invocation (the "ask_wbai" relay). Overridable in
# case the registered tool name differs in a given registry.
_REMOTE_TOOL = os.getenv("WB_AI_MCP_TOOL", "ask_wbai").strip() or "ask_wbai"

# Reviewer lenses Working Backwards AI supports. Passed through in the
# prompt so the service applies the requested critique persona.
_VALID_LENSES = frozenset({
    "customer", "senior_leader", "responsible_ai", "product_manager", "all",
})


class WorkingBackwardsAICritiqueInput(BaseModel):
    """Input schema for WorkingBackwardsAICritiqueTool."""

    document_text: str = Field(
        ...,
        description=(
            "The full PRFAQ (or 5-Customer-Questions) draft text to "
            "pressure-test. Sent verbatim to Working Backwards AI."
        ),
    )
    lens: str = Field(
        default="all",
        description=(
            "Which reviewer lens to apply: 'customer', 'senior_leader', "
            "'responsible_ai', 'product_manager', or 'all' (default)."
        ),
    )
    focus: str = Field(
        default="",
        description=(
            "Optional free-text focus for the critique (e.g. 'the pricing "
            "assumption in the press release'). Appended to the request."
        ),
    )


class WorkingBackwardsAICritiqueTool(BaseTool):
    """Pressure-test a PRFAQ draft via the internal Working Backwards AI service.

    Sends the draft to Working Backwards AI's MCP server and returns its
    persona/bar-raiser critique. Requires an MCP Gateway client binary
    (default ``wb-ai-mcp``, override with ``WB_AI_MCP_BINARY``) on PATH and
    a valid Midway session. Auth is handled by the binary.
    """

    name: str = "working_backwards_ai_critique"
    description: str = (
        "Pressure-test a PRFAQ or 5-Customer-Questions draft via the "
        "internal Working Backwards AI service. Returns critique from "
        "simulated customer personas and domain-expert reviewers (customer, "
        "senior_leader, responsible_ai, product_manager). Use it to surface "
        "blind spots before a human stakeholder review, then address the "
        "critique in a revision. Does not replace human review."
    )
    args_schema: Type[BaseModel] = WorkingBackwardsAICritiqueInput

    def _run(
        self,
        document_text: str = "",
        lens: str = "all",
        focus: str = "",
    ) -> str:
        lens_clean = (lens or "all").strip().lower()
        if lens_clean not in _VALID_LENSES:
            lens_clean = "all"

        _mcp_stdio.log_call(
            _CALL_LOG_PATH,
            "invocation",
            {
                "lens": lens_clean,
                "focus": focus,
                "document_chars": len(document_text or ""),
            },
        )

        if not (document_text or "").strip():
            return "Error: document_text is required and must be non-empty."

        # Transparent relay: forward the draft verbatim, with a minimal
        # instruction naming the requested lens. Working Backwards AI owns
        # the coaching logic; we do not interpret or rephrase.
        lens_phrase = (
            "all reviewer lenses (customer, senior leader, responsible AI, "
            "product manager)"
            if lens_clean == "all"
            else f"the {lens_clean.replace('_', ' ')} lens"
        )
        prompt = (
            f"Review this Working Backwards document using {lens_phrase}. "
            f"Surface blind spots, unstated assumptions, and weak points a "
            f"stakeholder would challenge."
        )
        if focus.strip():
            prompt += f" Focus especially on: {focus.strip()}."
        prompt += f"\n\n<document>\n{document_text}\n</document>"

        arguments = {"prompt": prompt}

        try:
            result = _mcp_stdio.call_stdio_mcp(
                _BINARY_NAME,
                _REMOTE_TOOL,
                arguments,
                timeout=120.0,  # persona critique can take longer than a search
            )
            _mcp_stdio.log_call(
                _CALL_LOG_PATH,
                "response",
                {"lens": lens_clean, "response_chars": len(result), "response_preview": result[:300]},
            )
            return result
        except FileNotFoundError as exc:
            msg = (
                f"{_BINARY_NAME} binary not found on PATH; the Working "
                f"Backwards AI MCP client is not installed. Install the MCP "
                f"Gateway client and run 'mwinit -f', or set WB_AI_MCP_BINARY "
                f"to the installed client name. ({exc})"
            )
            _mcp_stdio.log_call(_CALL_LOG_PATH, "binary_missing", {"message": str(exc)})
            return msg
        except asyncio.TimeoutError:
            msg = "Working Backwards AI critique timed out."
            _mcp_stdio.log_call(_CALL_LOG_PATH, "timeout", {})
            return msg
        except Exception as exc:  # noqa: BLE001
            msg = f"Error connecting to Working Backwards AI: {exc}"
            _mcp_stdio.log_call(
                _CALL_LOG_PATH,
                "exception",
                {"type": type(exc).__name__, "message": str(exc)},
            )
            return msg
