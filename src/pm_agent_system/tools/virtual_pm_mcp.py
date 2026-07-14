"""Virtual PM critique tool (optional, internal Amazon).

Composes the PRFAQ stage with the internal ``virtual-pm-mcp`` server (Virtual
Product Manager), a second critique lens alongside ``WorkingBackwardsAICritiqueTool``.
Virtual PM reviews a spec and returns a 0-100 score across 8 PM personas
(``sentinel_review``). It is analogous to Working Backwards AI: an external
service that owns its own review logic, invoked via MCP rather than
re-implemented locally.

⚠️ ASSUMED CONTRACT (unit-tested, live smoke test pending): the
``virtual-pm-mcp`` binary would not install on the build host this session (the
AIM registry lists it "In development" and toolbox could not resolve it), so
the ``sentinel_review`` arg shape is UNVERIFIED. The document is forwarded under
a ``spec`` argument (best guess); both the remote tool name
(``VIRTUAL_PM_MCP_TOOL``) and the binary (``VIRTUAL_PM_MCP_BINARY``) are
env-overridable so a live smoke test can correct the contract without a code
change.

Design notes (mirroring ``working_backwards_ai``):
- Transport is stdio via the MCP Gateway client binary (spawn-per-call, Midway
  auth handled by the binary).
- Transparent relay: forward the draft verbatim, return the service's critique
  verbatim. This tool does not interpret or rephrase.
- Fail-soft: when the binary is not on PATH, ``_run`` returns a descriptive
  error string and never raises, so the OSS pipeline runs unchanged.

Attached to the PRFAQ agent only when the binary is present (see ``crew.py``
``_virtual_pm_enabled``).
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

_CALL_LOG_PATH = Path(os.getenv("OUTPUT_DIR", "./output")) / "virtual_pm_mcp_calls.log"

# MCP Gateway client binary. Overridable; defaults to the AIM registry id.
_BINARY_NAME = os.getenv("VIRTUAL_PM_MCP_BINARY", "virtual-pm-mcp").strip() or "virtual-pm-mcp"

# The spec-review tool (0-100 score, 8 personas). Env-overridable.
_REMOTE_TOOL = os.getenv("VIRTUAL_PM_MCP_TOOL", "sentinel_review").strip() or "sentinel_review"


class VirtualPMCritiqueInput(BaseModel):
    """Input schema for VirtualPMCritiqueTool."""

    document_text: str = Field(
        ...,
        description=(
            "The full PRFAQ (or spec) draft text to review. Sent verbatim to "
            "Virtual PM's sentinel_review."
        ),
    )
    focus: str = Field(
        default="",
        description=(
            "Optional free-text focus for the review (e.g. 'the success "
            "metrics'). Appended to the request."
        ),
    )


class VirtualPMCritiqueTool(BaseTool):
    """Pressure-test a PRFAQ draft via the internal Virtual PM service.

    Sends the draft to Virtual PM's MCP server and returns its 0-100 score and
    8-persona critique. A second critique lens alongside Working Backwards AI.
    Requires the ``virtual-pm-mcp`` binary on PATH (override with
    ``VIRTUAL_PM_MCP_BINARY``) and a live Midway session; auth is handled by the
    binary. Does not replace human review.
    """

    name: str = "virtual_pm_critique"
    description: str = (
        "Pressure-test a PRFAQ or spec draft via the internal Virtual Product "
        "Manager service. Returns a 0-100 score and critique across 8 PM "
        "personas. A second critique lens alongside working_backwards_ai_critique. "
        "Use it to surface blind spots before a human review, then address the "
        "critique in a revision. Does not replace human review."
    )
    args_schema: Type[BaseModel] = VirtualPMCritiqueInput

    def _run(self, document_text: str = "", focus: str = "") -> str:
        _mcp_stdio.log_call(
            _CALL_LOG_PATH,
            "invocation",
            {"focus": focus, "document_chars": len(document_text or "")},
        )

        if not (document_text or "").strip():
            return "Error: document_text is required and must be non-empty."

        # Transparent relay: forward the draft verbatim. Virtual PM owns the
        # review logic; we do not interpret or rephrase. The `spec` argument is
        # the assumed field name (env-overridable tool aside, the arg shape is
        # unverified — flagged for a live smoke test).
        arguments: dict = {"spec": document_text}
        if focus.strip():
            arguments["focus"] = focus.strip()

        try:
            result = _mcp_stdio.call_stdio_mcp(
                _BINARY_NAME,
                _REMOTE_TOOL,
                arguments,
                timeout=120.0,  # persona review can take longer than a search
            )
            _mcp_stdio.log_call(
                _CALL_LOG_PATH,
                "response",
                {"response_chars": len(result), "response_preview": result[:300]},
            )
            return result
        except FileNotFoundError as exc:
            msg = (
                f"{_BINARY_NAME} binary not found on PATH; the Virtual PM MCP "
                f"client is not installed. Install the MCP Gateway client and "
                f"run 'mwinit -f', or set VIRTUAL_PM_MCP_BINARY to the installed "
                f"client name. ({exc})"
            )
            _mcp_stdio.log_call(_CALL_LOG_PATH, "binary_missing", {"message": str(exc)})
            return msg
        except asyncio.TimeoutError:
            msg = "Virtual PM critique timed out."
            _mcp_stdio.log_call(_CALL_LOG_PATH, "timeout", {})
            return msg
        except Exception as exc:  # noqa: BLE001 — fail soft like the other read tools
            msg = f"Error connecting to Virtual PM: {exc}"
            _mcp_stdio.log_call(
                _CALL_LOG_PATH,
                "exception",
                {"type": type(exc).__name__, "message": str(exc)},
            )
            return msg
