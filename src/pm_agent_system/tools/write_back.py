"""Gated write-back helpers for internal Amazon systems (optional).

Unlike every other internal-MCP integration in this repo, the functions here
**write** to outward-facing systems. They are NOT CrewAI tools and are NEVER
attached to an agent: publishing a document or creating a task is a human
action the PM invokes from the CLI *after* approving an artifact, always
behind an explicit ``input()`` confirmation (see the ``publish-doc``,
``seed-taskei`` handlers in ``main.py``). Nothing in this module prompts; the
confirmation lives in the command handler so the write helper stays a thin,
testable transport wrapper.

Transport mirrors ``working_backwards_ai`` / ``builder_mcp``: stdio to an MCP
Gateway client binary via ``_mcp_stdio.call_stdio_mcp``. Auth (the Midway
cookie) is handled by the binary; this module never touches auth material.

Design notes:
- **Fail-soft, exactly like the read tools.** When the binary is not on PATH
  (or Midway is absent), every helper returns a descriptive string beginning
  with ``"Error"`` and never raises. Callers detect failure via
  ``is_write_error`` rather than exceptions, so a missing binary degrades the
  command to a no-op message instead of a crash.
- **Pluggable publish providers, each with its own binary.** Document
  publishing routes through a ``PUBLISH_PROVIDERS`` registry keyed by target
  name; every entry carries ``(binary, remote_tool, arg_builder)``. Quip and
  Taskei speak to the builder-mcp binary (Midway auth); SharePoint speaks to a
  *separate* ``sharepoint-mcp`` binary (FedAuth cookie auth); Pippin speaks to
  ``python-pippin-mcp``. The binary owns its own auth in every case, so this
  module still never touches auth material — it only routes each provider to
  the right binary.
- **Env-overridable remote contracts.** The remote MCP tool names are the
  live gateway names (``QuipEditor``, ``TaskeiCreateTask``,
  ``create_artifact`` for Pippin) but are overridable via env vars (mirroring
  ``WB_AI_MCP_TOOL``) so a later live smoke test can correct an arg-shape
  assumption without a code change. The SharePoint create-document tool name
  is *assumed* (its binary would not install this session) and is likewise
  env-overridable via ``WRITE_BACK_SHAREPOINT_TOOL``.
- **JSONL call logging** via ``_mcp_stdio.log_call`` to
  ``output/write_back_calls.log``, same as the read tools.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Callable

from pm_agent_system.tools import _mcp_stdio

logger = logging.getLogger(__name__)

_CALL_LOG_PATH = Path(os.getenv("OUTPUT_DIR", "./output")) / "write_back_calls.log"

# MCP Gateway client binary that exposes the builder-mcp write tools (Quip +
# Taskei). Same binary as the read tools; overridable for whichever gateway
# client is installed. This is the default binary for _call_write, so Taskei
# and Quip keep their existing behavior after the per-provider-binary refactor.
_BINARY_NAME = os.getenv("WRITE_BACK_MCP_BINARY", "builder-mcp").strip() or "builder-mcp"

# Remote builder-mcp tool names. Confirmed against the live builder-mcp
# gateway registry (2026-07); overridable in case a registry registers them
# under a different name.
_QUIP_TOOL = os.getenv("WRITE_BACK_QUIP_TOOL", "QuipEditor").strip() or "QuipEditor"
_TASKEI_TOOL = os.getenv("WRITE_BACK_TASKEI_TOOL", "TaskeiCreateTask").strip() or "TaskeiCreateTask"

# SharePoint is a SEPARATE MCP binary (`sharepoint-mcp`) with FedAuth-cookie
# auth, not the builder-mcp Midway path. The binary owns its own auth exactly
# as builder-mcp does, so the fail-soft contract here is unchanged; only the
# binary differs. The create-document tool name is ASSUMED: the sharepoint-mcp
# binary would not install on the build host this session (the AIM registry
# lists it "In development" and toolbox could not resolve it), so its 12-tool
# contract is unverified. `create_document` is a best-guess default and is
# env-overridable so a live smoke test can correct it without a code change.
_SHAREPOINT_BINARY = os.getenv("WRITE_BACK_SHAREPOINT_BINARY", "sharepoint-mcp").strip() or "sharepoint-mcp"
_SHAREPOINT_TOOL = os.getenv("WRITE_BACK_SHAREPOINT_TOOL", "create_document").strip() or "create_document"

# Pippin (Amazon's canonical PRFAQ/BRD/design-doc platform) via the
# `python-pippin-mcp` binary. The create-artifact contract is CONFIRMED against
# the connected python-pippin-mcp server: create_artifact(project_id, name,
# content, description?) — note there is no `format` argument (content is a
# plain string). Tool name env-overridable to match the WB-AI idiom.
_PIPPIN_BINARY = os.getenv("PIPPIN_MCP_BINARY", "python-pippin-mcp").strip() or "python-pippin-mcp"
_PIPPIN_TOOL = os.getenv("WRITE_BACK_PIPPIN_TOOL", "create_artifact").strip() or "create_artifact"

# Per-call timeout. Doc creation and task creation are single writes, but the
# gateway can be slow to spin up, so match the WB-AI generous window.
_WRITE_TIMEOUT = 120.0

# Taskei task type used for the parent container and the per-requirement
# children. Overridable so a room whose workflow forbids EPIC/TASK can adapt.
_TASKEI_EPIC_TYPE = os.getenv("WRITE_BACK_TASKEI_EPIC_TYPE", "EPIC").strip() or "EPIC"
_TASKEI_TASK_TYPE = os.getenv("WRITE_BACK_TASKEI_TASK_TYPE", "TASK").strip() or "TASK"


# ---------------------------------------------------------------------------
# Error helper
# ---------------------------------------------------------------------------
def is_write_error(result: str) -> bool:
    """True when a helper's return value denotes failure rather than a URL.

    Write helpers never raise; they return either a resource URL/identifier
    (success) or a descriptive string starting with ``"Error"`` (failure).
    Handlers use this to decide whether to report success or a soft failure.
    """
    return result.strip().lower().startswith("error")


def _binary_missing_message(context: str, binary: str = _BINARY_NAME) -> str:
    return (
        f"Error: {binary} binary not found on PATH; cannot {context}. "
        f"Install the MCP Gateway client "
        f"('toolbox install mcp-registry && mcp-registry install {binary}') "
        f"and run 'mwinit -f'."
    )


# ---------------------------------------------------------------------------
# URL / identifier extraction
# ---------------------------------------------------------------------------
_URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")


# Pippin web base. The create_artifact response carries no URL (see
# _pippin_extract_url), so the addressable artifact URL is constructed from the
# projectId + designId in the response. Overridable for a different Pippin host.
_PIPPIN_BASE_URL = os.getenv("PIPPIN_BASE_URL", "https://pippin.sara.amazon.dev").strip().rstrip("/") or "https://pippin.sara.amazon.dev"


def _pippin_extract_url(raw: str, project_id: str = "") -> str:
    """Build the canonical Pippin artifact URL from a create_artifact response.

    CONFIRMED LIVE 2026-07-14: python-pippin-mcp's ``create_artifact`` returns a
    JSON object (``{"design": {"designId": ..., "projectId": ..., ...}}``) with
    **no URL field** — so the generic ``_extract_url`` would fall back to
    dumping the whole JSON blob as the "document URL". The addressable artifact
    lives at ``{base}/architect/{projectId}?artifact={designId}`` (the URL shape
    the Pippin MCP server documents), so we parse the ids out and construct it.

    Falls back to ``_extract_url`` when the response is not the expected JSON
    (e.g. a future server revision that returns a real URL, or an unparseable
    body), so this never regresses a response that already contains a URL.
    """
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return _extract_url(raw, fallback_label="pippin document")

    design = payload.get("design", payload) if isinstance(payload, dict) else {}
    if not isinstance(design, dict):
        design = {}
    design_id = str(design.get("designId", "") or "").strip()
    proj = str(design.get("projectId", "") or project_id or "").strip()
    if design_id and proj:
        return f"{_PIPPIN_BASE_URL}/architect/{proj}?artifact={design_id}"
    # Parsed, but the ids we need are absent — fall back to generic handling.
    return _extract_url(raw, fallback_label="pippin document")


def _extract_url(raw: str, fallback_label: str = "resource") -> str:
    """Pull the first URL out of an MCP text response.

    The write tools return free-text (a confirmation sentence plus the new
    doc/task URL); the exact response shape is not pinned by the tool schema,
    so we scan for the first http(s) URL. When none is present we return the
    raw response verbatim so the caller still sees whatever the service said
    (and the recap can flag URL extraction as needing a live smoke test).
    """
    match = _URL_RE.search(raw or "")
    if match:
        return match.group(0)
    stripped = (raw or "").strip()
    if stripped:
        return stripped
    return f"(created {fallback_label}; no URL returned)"


# A Taskei short-id (e.g. "T-1234", "EPIC-1") or a UUID — the identifier forms
# TaskeiCreateTask accepts for parentTask. Used to derive a parent reference
# from a create response, whose full text/URL is NOT a valid parent id.
_TASK_ID_RE = re.compile(
    r"\b([A-Za-z][A-Za-z0-9]*-\d+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b"
)


def extract_task_ref(create_result: str) -> str:
    """Derive a Taskei parent identifier from a successful create result.

    ``create_taskei_task`` / ``create_taskei_epic`` return a value suitable for
    *display* (a URL, or raw confirmation text). That value is NOT a valid
    ``parentTask`` identifier — Taskei's parentTask wants a task ID, not a
    document URL or a sentence. This derives the best-available id:

    - If the result is a URL, take its last path segment (the task id in the
      canonical Taskei URL shape ``.../tasks/<id>``).
    - Otherwise, return the first task-id-like token (``ABC-123`` or a UUID).
    - Failing both, return the stripped result unchanged (best effort).

    The exact live response shape is unconfirmed (needs a live smoke test), so
    this is deliberately tolerant rather than strict.
    """
    s = (create_result or "").strip()
    if not s:
        return s
    url_match = _URL_RE.search(s)
    if url_match:
        url = url_match.group(0).split("?")[0].split("#")[0].rstrip("/")
        segment = url.rsplit("/", 1)[-1]
        if segment:
            return segment
    id_match = _TASK_ID_RE.search(s)
    if id_match:
        return id_match.group(0)
    return s


# ---------------------------------------------------------------------------
# Low-level call wrapper (shared by every helper)
# ---------------------------------------------------------------------------
def _call_write(
    remote_tool: str,
    arguments: dict,
    *,
    context: str,
    log_details: dict,
    binary: str = _BINARY_NAME,
) -> str:
    """Invoke one write tool, returning its raw text or an ``Error: ...`` string.

    ``binary`` selects the MCP Gateway client to spawn. It defaults to the
    builder-mcp binary so the Taskei helpers (and any caller not passing it)
    keep their behavior; the publish providers thread their own binary
    (SharePoint uses a separate FedAuth binary, Pippin uses python-pippin-mcp).

    Fail-soft on every failure mode (missing binary, timeout, transport /
    protocol error), matching the read tools. Never raises.
    """
    _mcp_stdio.log_call(
        _CALL_LOG_PATH, "invocation", {"tool": remote_tool, "binary": binary, **log_details}
    )

    if not _mcp_stdio.is_binary_available(binary):
        msg = _binary_missing_message(context, binary)
        _mcp_stdio.log_call(_CALL_LOG_PATH, "binary_missing", {"tool": remote_tool, "binary": binary})
        return msg

    try:
        result = _mcp_stdio.call_stdio_mcp(
            binary,
            remote_tool,
            arguments,
            timeout=_WRITE_TIMEOUT,
        )
        _mcp_stdio.log_call(
            _CALL_LOG_PATH,
            "response",
            {"tool": remote_tool, "response_chars": len(result), "response_preview": result[:300]},
        )
        return result
    except FileNotFoundError as exc:
        _mcp_stdio.log_call(_CALL_LOG_PATH, "binary_missing", {"tool": remote_tool, "binary": binary, "message": str(exc)})
        return _binary_missing_message(context, binary)
    except asyncio.TimeoutError:
        _mcp_stdio.log_call(_CALL_LOG_PATH, "timeout", {"tool": remote_tool})
        return f"Error: {context} timed out after {_WRITE_TIMEOUT:.0f}s."
    except Exception as exc:  # noqa: BLE001 — fail soft like the read tools
        _mcp_stdio.log_call(
            _CALL_LOG_PATH,
            "exception",
            {"tool": remote_tool, "type": type(exc).__name__, "message": str(exc)},
        )
        return f"Error: could not {context}: {exc}"


# ---------------------------------------------------------------------------
# Document publish — pluggable providers
# ---------------------------------------------------------------------------
def _quip_publish_args(title: str, markdown: str, folder: str) -> dict:
    """Build QuipEditor create-document arguments.

    Omitting ``documentId`` tells QuipEditor to create a new document.
    ``memberIds`` is the comma-separated folder/user access list — the target
    a ``--folder`` argument maps onto.
    """
    args: dict = {"title": title, "content": markdown, "format": "markdown"}
    if folder:
        args["memberIds"] = folder
    return args


def _sharepoint_publish_args(title: str, markdown: str, folder: str) -> dict:
    """Build sharepoint-mcp create-document arguments.

    ASSUMED CONTRACT (unit-tested, live smoke test pending): the sharepoint-mcp
    binary would not install this session, so its exact create-document arg
    shape is unverified. This maps to the most conventional shape — a title,
    the markdown content, its format, and a single destination string carrying
    the SharePoint site/library/folder path (the ``--folder`` argument, kept
    identical to Quip's shape per the destination-model decision). ``folder``
    is only sent when non-empty; the SharePoint MCP is expected to fall back to
    a default library otherwise. Correct any of these keys via a live smoke
    test — the tool name itself is env-overridable (WRITE_BACK_SHAREPOINT_TOOL)
    and the arg keys can follow.
    """
    args: dict = {"title": title, "content": markdown, "format": "markdown"}
    if folder:
        args["destination"] = folder
    return args


def _pippin_publish_args(title: str, markdown: str, folder: str) -> dict:
    """Build python-pippin-mcp create_artifact arguments.

    CONFIRMED LIVE 2026-07-14 against python-pippin-mcp:
    ``create_artifact(project_id, name, content, description?)``. There is no
    ``format`` argument — ``content`` is a plain string. Pippin has no sensible
    OSS default project, so ``folder`` carries the required ``project_id``
    (threaded from ``--pippin-project`` / ``PIPPIN_PROJECT_ID`` by the CLI); an
    empty value is refused before we ever build args (see ``publish_document``).

    Response note: the tool returns JSON ``{"design": {"designId", "projectId",
    "docId", "version", ...}}`` with **no URL** — the addressable URL is built
    by ``_pippin_extract_url`` from projectId + designId.
    """
    return {"project_id": folder, "name": title, "content": markdown}


# Registry: target name -> (binary, remote tool name, argument builder).
#
# Each provider names the MCP Gateway client binary it speaks to, because they
# are not all the same binary: Quip rides the builder-mcp binary (Midway auth),
# SharePoint rides a separate `sharepoint-mcp` binary (FedAuth cookie), and
# Pippin rides `python-pippin-mcp`. PUBLISH_TARGETS is derived from the keys so
# the CLI validation updates automatically.
PUBLISH_PROVIDERS: dict[str, tuple[str, str, Callable[[str, str, str], dict]]] = {
    "quip": (_BINARY_NAME, _QUIP_TOOL, _quip_publish_args),
    "sharepoint": (_SHAREPOINT_BINARY, _SHAREPOINT_TOOL, _sharepoint_publish_args),
    "pippin": (_PIPPIN_BINARY, _PIPPIN_TOOL, _pippin_publish_args),
}

PUBLISH_TARGETS = tuple(PUBLISH_PROVIDERS)

# Targets that require a non-empty ``folder`` to carry a mandatory destination
# with no OSS default. Pippin's create_artifact requires a project_id (there is
# no sensible default), so publish_document refuses a blank folder for it,
# exactly as seed-taskei refuses a blank --taskei-room.
_FOLDER_REQUIRED_TARGETS = {"pippin"}


def publish_document(title: str, markdown: str, target: str = "quip", folder: str = "") -> str:
    """Publish *markdown* as a new document to *target*, returning its URL.

    Parameters
    ----------
    title
        Document title.
    markdown
        Full markdown body to publish (sent verbatim).
    target
        Provider key from ``PUBLISH_PROVIDERS`` (``"quip"``, ``"sharepoint"``,
        or ``"pippin"``).
    folder
        Optional provider-specific destination. Quip: comma-separated
        folder/user member IDs. SharePoint: site/library/folder path.
        Pippin: the target ``project_id`` — REQUIRED (no OSS default), so a
        blank value is refused for the Pippin target.

    Returns
    -------
    str
        The created document's URL on success, or a string beginning with
        ``"Error"`` on any failure (unknown target, missing destination,
        missing binary, transport error). Never raises.
    """
    target_clean = (target or "").strip().lower()
    provider = PUBLISH_PROVIDERS.get(target_clean)
    if provider is None:
        valid = ", ".join(sorted(PUBLISH_PROVIDERS)) or "(none configured)"
        return (
            f"Error: unknown publish target '{target}'. "
            f"Valid targets: {valid}."
        )
    if not (title or "").strip():
        return "Error: a non-empty title is required to publish a document."
    if not (markdown or "").strip():
        return "Error: refusing to publish an empty document."
    if target_clean in _FOLDER_REQUIRED_TARGETS and not (folder or "").strip():
        return (
            f"Error: publishing to {target_clean} requires a project/destination "
            f"id (--pippin-project or PIPPIN_PROJECT_ID); refusing without one."
        )

    binary, remote_tool, build_args = provider
    arguments = build_args(title, markdown, folder)
    raw = _call_write(
        remote_tool,
        arguments,
        context=f"publish document to {target_clean}",
        log_details={"target": target_clean, "title": title, "content_chars": len(markdown), "folder": folder},
        binary=binary,
    )
    if is_write_error(raw):
        return raw
    # Pippin's create_artifact returns JSON with no URL (confirmed live
    # 2026-07-14); build the canonical artifact URL from its ids. Other
    # providers return free-text that carries the URL, handled generically.
    if target_clean == "pippin":
        return _pippin_extract_url(raw, project_id=folder)
    return _extract_url(raw, fallback_label=f"{target_clean} document")


# ---------------------------------------------------------------------------
# Taskei task creation
# ---------------------------------------------------------------------------
def create_taskei_task(
    room: str,
    name: str,
    description: str,
    *,
    task_type: str = _TASKEI_TASK_TYPE,
    priority: str = "",
    parent_task: str = "",
) -> str:
    """Create one Taskei task, returning its URL/identifier.

    Parameters
    ----------
    room
        Taskei room UUID (required by the remote tool). Refused if empty.
    name
        Task title.
    description
        Task body (markdown accepted by Taskei).
    task_type
        Taskei task type (EPIC, TASK, STORY, ...). When *parent_task* is set,
        Taskei derives the child type from the parent, so this is advisory.
    priority
        Optional Taskei priority ("High" / "Medium" / "Low"). Omitted if blank
        or unrecognised.
    parent_task
        Optional parent task identifier to nest this task under.

    Returns
    -------
    str
        The created task's URL/identifier on success, or a string beginning
        with ``"Error"`` on failure. Never raises.
    """
    if not (room or "").strip():
        return "Error: a Taskei room ID is required (--taskei-room or TASKEI_ROOM_ID)."
    if not (name or "").strip():
        return "Error: a non-empty task name is required."

    arguments: dict = {
        "name": name,
        "description": description or "",
        "roomId": room.strip(),
    }
    if task_type:
        arguments["type"] = task_type
    if priority and priority.strip().capitalize() in {"High", "Medium", "Low"}:
        arguments["priority"] = priority.strip().capitalize()
    if parent_task and parent_task.strip():
        arguments["parentTask"] = parent_task.strip()

    raw = _call_write(
        _TASKEI_TOOL,
        arguments,
        context="create Taskei task",
        log_details={"room": room, "name": name, "type": task_type, "parent": parent_task},
    )
    if is_write_error(raw):
        return raw
    return _extract_url(raw, fallback_label="Taskei task")


def create_taskei_epic(room: str, name: str, description: str, *, priority: str = "") -> str:
    """Create a Taskei EPIC to parent a batch of requirement tasks under.

    Thin wrapper over :func:`create_taskei_task` with the EPIC type. Returns
    the EPIC's URL/identifier, or an ``"Error"`` string on failure.
    """
    return create_taskei_task(
        room,
        name,
        description,
        task_type=_TASKEI_EPIC_TYPE,
        priority=priority,
    )
