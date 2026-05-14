"""Agent harness for capturing, replaying, and evaluating crew executions.

Public API
----------
run_crew       – execute a crew through the harness with full interception
load_record    – read a RunRecord JSON file from disk
diff_manifests – compare two RunManifests and report differing fields
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .exceptions import HarnessConfigError, ManifestDriftError
from .interceptors import LLMInterceptor, ToolInterceptor
from .logging import emit_event
from .meters import CostMeter, LatencyMeter
from .models import PromptSnapshot, RunManifest, RunRecord, SpanType
from .trace import TraceBuilder


# Path to config files (relative to project root).
_CONFIG_DIR = Path(__file__).resolve().parents[2] / "src" / "pm_agent_system" / "config"

# Environment flag keys that affect crew behaviour.
_ENV_FLAG_KEYS = [
    "LLM_PROVIDER",
    "DOVETAIL_API_TOKEN",
    "BUILDER_MCP_TOKEN",
    "OUTLOOK_MCP_TOKEN",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256_hex(data: str | bytes) -> str:
    """Return the lowercase hex SHA-256 digest of *data*."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _read_config_file(name: str) -> str:
    """Read a config file from *_CONFIG_DIR*, raising on failure."""
    path = _CONFIG_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise HarnessConfigError(str(path)) from exc


def _capture_manifest(
    crew: Any,
    inputs: dict[str, str],
) -> RunManifest:
    """Build a :class:`RunManifest` from the current environment and crew."""
    from pm_agent_system.crew import _MODEL  # noqa: WPS433 – runtime import

    agents_yaml = _read_config_file("agents.yaml")
    tasks_yaml = _read_config_file("tasks.yaml")

    # Extract tool class names per agent.
    tool_names_by_agent: dict[str, list[str]] = {}
    for ag in getattr(crew, "agents", []):
        agent_name = getattr(ag, "role", None) or getattr(ag, "name", None) or "unknown"
        tools = getattr(ag, "tools", []) or []
        tool_names_by_agent[agent_name] = [type(t).__name__ for t in tools]

    env_flags = {key: bool(os.getenv(key, "").strip()) for key in _ENV_FLAG_KEYS}

    input_brief_hash = _sha256_hex(json.dumps(inputs, sort_keys=True, default=str))

    return RunManifest(
        model_id=_MODEL,
        agents_yaml_hash=_sha256_hex(agents_yaml),
        tasks_yaml_hash=_sha256_hex(tasks_yaml),
        tool_names_by_agent=tool_names_by_agent,
        env_flags=env_flags,
        input_brief_hash=input_brief_hash,
    )


def _capture_prompt_snapshots(crew: Any) -> list[PromptSnapshot]:
    """Capture interpolated prompt text from all agents and tasks.

    After kickoff, each task and agent has its interpolated role, goal,
    backstory, description, and expected_output set. We pair them by
    the agent assigned to each task.
    """
    snapshots: list[PromptSnapshot] = []
    for idx, task_obj in enumerate(getattr(crew, "tasks", [])):
        agent_obj = getattr(task_obj, "agent", None)
        if agent_obj is None:
            continue

        agent_role = (getattr(agent_obj, "role", None) or "").strip()
        agent_goal = (getattr(agent_obj, "goal", None) or "").strip()
        agent_backstory = (getattr(agent_obj, "backstory", None) or "").strip()
        agent_name = agent_role or (getattr(agent_obj, "name", None) or "unknown").strip()

        task_description = (getattr(task_obj, "description", None) or "").strip()
        task_expected_output = (getattr(task_obj, "expected_output", None) or "").strip()
        task_name = (getattr(task_obj, "name", None) or "unknown_task").strip()

        snapshots.append(
            PromptSnapshot(
                agent_role=agent_role,
                agent_goal=agent_goal,
                agent_backstory=agent_backstory,
                task_description=task_description,
                task_expected_output=task_expected_output,
                agent_name=agent_name,
                task_name=task_name,
                sequence_index=idx,
            )
        )
    return snapshots


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_crew(
    crew: Any,
    inputs: dict[str, str],
    replay_path: str | None = None,
    output_path: str | None = None,
    strict_manifest: bool = False,
) -> RunRecord:
    """Execute a crew through the harness with full interception.

    Parameters
    ----------
    crew:
        A CrewAI ``Crew`` object (already configured with agents/tasks).
    inputs:
        The dictionary of inputs passed to ``crew.kickoff``.
    replay_path:
        When provided, the path to a stored :class:`RunRecord` JSON file.
        The harness will run in replay mode, serving canned LLM and tool
        responses instead of calling live APIs.
    output_path:
        When provided, the :class:`RunRecord` is written to this path as
        2-space-indented JSON after execution.
    strict_manifest:
        When ``True`` **and** ``replay_path`` is set, the harness raises
        :class:`ManifestDriftError` if the stored manifest differs from
        the current configuration.  When ``False`` (default), a warning
        is emitted instead.

    Returns
    -------
    RunRecord
        The complete run record for this execution.
    """
    from pm_agent_system.crew import _llm as original_llm_factory  # noqa: WPS433

    run_id = str(uuid.uuid4())

    # 1. Capture the current manifest (validates config files exist).
    manifest = _capture_manifest(crew, inputs)

    # 2. Replay setup (if applicable).
    replay_record: RunRecord | None = None
    replay_llm_calls = None
    replay_tool_calls = None

    if replay_path is not None:
        replay_record = load_record(replay_path)
        diffs = diff_manifests(replay_record.manifest, manifest)
        if diffs:
            field_names = list(diffs.keys())
            if strict_manifest:
                raise ManifestDriftError(field_names)
            else:
                warnings.warn(
                    f"Manifest drift detected. Differing fields: {', '.join(field_names)}",
                    stacklevel=2,
                )
        replay_llm_calls = replay_record.llm_calls
        replay_tool_calls = replay_record.tool_calls

    # 3. Wire up trace builder.
    trace_builder = TraceBuilder()
    root_span_id = trace_builder.start_span(SpanType.crew, metadata={"run_id": run_id})

    emit_event("crew_start", span_id=root_span_id, run_id=run_id)

    # 4. Wire up interceptors.
    llm_interceptor = LLMInterceptor(
        original_llm_factory=original_llm_factory,
        trace_builder=trace_builder,
        replay_calls=replay_llm_calls,
    )
    tool_interceptor = ToolInterceptor(
        trace_builder=trace_builder,
        replay_calls=replay_tool_calls,
    )

    # Wrap all tools on all agents.
    for ag in getattr(crew, "agents", []):
        for tool in getattr(ag, "tools", []) or []:
            tool_interceptor.wrap_tool(tool)

    # Wrap the LLM on each agent with interception (preserving any routing).
    for ag in getattr(crew, "agents", []):
        agent_name = (getattr(ag, "role", None) or getattr(ag, "name", None) or "").strip()
        ag.llm = llm_interceptor.wrap_existing_llm(ag.llm, agent_name=agent_name)

    # 5. Execute the crew.
    try:
        crew.kickoff(inputs=inputs)
    finally:
        # 6. End the root span regardless of success/failure.
        trace_builder.end_span(root_span_id)
        emit_event("crew_end", span_id=root_span_id, run_id=run_id)

    # 7. Build trace and compute summaries.
    trace = trace_builder.build_trace()
    cost_summary = CostMeter.compute(llm_interceptor.records)
    latency_summary = LatencyMeter.compute(trace)

    # 8. Collect agent outputs (best-effort).
    agent_outputs: dict[str, str] = {}
    for task_obj in getattr(crew, "tasks", []):
        output = getattr(task_obj, "output", None)
        if output is not None:
            task_name = getattr(task_obj, "name", None) or "unknown_task"
            agent_outputs[task_name] = str(output)

    # 8b. Capture prompt snapshots (interpolated agent/task text).
    prompt_snapshots = _capture_prompt_snapshots(crew)

    # 9. Assemble the RunRecord.
    record = RunRecord(
        run_id=run_id,
        manifest=manifest,
        prompt_snapshots=prompt_snapshots,
        tool_calls=tool_interceptor.records,
        llm_calls=llm_interceptor.records,
        trace=trace,
        cost_summary=cost_summary,
        latency_summary=latency_summary,
        agent_outputs=agent_outputs,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    # 10. Optionally persist.
    if output_path is not None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(
            record.model_dump_json(indent=2),
            encoding="utf-8",
        )

    return record


def load_record(path: str) -> RunRecord:
    """Read a RunRecord JSON file and return a validated Pydantic model.

    Parameters
    ----------
    path:
        Filesystem path to a JSON file produced by :func:`run_crew`.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    pydantic.ValidationError
        If the JSON content does not match the :class:`RunRecord` schema.
    """
    content = Path(path).read_text(encoding="utf-8")
    return RunRecord.model_validate_json(content)


def diff_manifests(a: RunManifest, b: RunManifest) -> dict[str, tuple]:
    """Compare two :class:`RunManifest` instances field-by-field.

    Returns
    -------
    dict[str, tuple]
        A mapping of ``{field_name: (old_value, new_value)}`` for every
        field where the two manifests differ.  An empty dict means the
        manifests are identical.
    """
    diffs: dict[str, tuple] = {}
    for field_name in RunManifest.model_fields:
        val_a = getattr(a, field_name)
        val_b = getattr(b, field_name)
        if val_a != val_b:
            diffs[field_name] = (val_a, val_b)
    return diffs
