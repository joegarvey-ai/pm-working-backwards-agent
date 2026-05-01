"""Custom Hypothesis strategies for generating harness test data.

Provides composite strategies that produce valid instances of every
harness data model.  Used by ``tests/test_harness_properties.py`` to
drive the 17 correctness property tests.
"""

from __future__ import annotations

import string
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import hypothesis.strategies as st

from pm_agent_system.pricing import MODEL_PRICING, estimate_cost

from tests.harness.models import (
    CostSummary,
    LatencySummary,
    LLMCallRecord,
    RunManifest,
    RunRecord,
    Span,
    SpanType,
    ToolCallRecord,
    Trace,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_SAFE_TEXT = st.text(
    alphabet=string.ascii_letters + string.digits + " _-",
    min_size=1,
    max_size=50,
)

_MODEL_IDS = list(MODEL_PRICING.keys())

_SHA256_HEX = st.text(
    alphabet=string.hexdigits[:16],  # 0-9a-f
    min_size=64,
    max_size=64,
)


# ---------------------------------------------------------------------------
# RunManifest strategy
# ---------------------------------------------------------------------------


@st.composite
def run_manifest_strategy(draw: st.DrawFn) -> RunManifest:
    """Generate a valid RunManifest."""
    model_id = draw(st.sampled_from(_MODEL_IDS))
    agents_yaml_hash = draw(_SHA256_HEX)
    tasks_yaml_hash = draw(_SHA256_HEX)

    # 1-4 agents, each with 0-3 tool names
    agent_names = draw(
        st.lists(_SAFE_TEXT, min_size=1, max_size=4, unique=True)
    )
    tool_names_by_agent = {
        name: draw(st.lists(_SAFE_TEXT, min_size=0, max_size=3))
        for name in agent_names
    }

    env_flags = {
        "LLM_PROVIDER": draw(st.booleans()),
        "DOVETAIL_API_TOKEN": draw(st.booleans()),
        "BUILDER_MCP_TOKEN": draw(st.booleans()),
        "OUTLOOK_MCP_TOKEN": draw(st.booleans()),
    }

    input_brief_hash = draw(_SHA256_HEX)

    return RunManifest(
        model_id=model_id,
        agents_yaml_hash=agents_yaml_hash,
        tasks_yaml_hash=tasks_yaml_hash,
        tool_names_by_agent=tool_names_by_agent,
        env_flags=env_flags,
        input_brief_hash=input_brief_hash,
    )


# ---------------------------------------------------------------------------
# LLMCallRecord strategy
# ---------------------------------------------------------------------------


@st.composite
def llm_call_record_strategy(
    draw: st.DrawFn,
    min_timestamp: float = 0.0,
) -> LLMCallRecord:
    """Generate a valid LLMCallRecord.

    The estimated_cost_usd is computed via estimate_cost so that the
    cost is consistent with the model and token counts.

    min_timestamp ensures monotonically increasing timestamps when
    generating lists.
    """
    model_id = draw(st.sampled_from(_MODEL_IDS))
    input_tokens = draw(st.integers(min_value=0, max_value=10000))
    output_tokens = draw(st.integers(min_value=0, max_value=10000))
    cost = estimate_cost(model_id, input_tokens, output_tokens)

    agent_name = draw(_SAFE_TEXT)
    task_name = draw(_SAFE_TEXT)

    timestamp = draw(
        st.floats(
            min_value=min_timestamp,
            max_value=min_timestamp + 1000.0,
            allow_nan=False,
            allow_infinity=False,
        )
    )

    duration = draw(
        st.floats(
            min_value=0.0,
            max_value=1000.0,
            allow_nan=False,
            allow_infinity=False,
        )
    )

    return LLMCallRecord(
        model_id=model_id,
        input_messages=[{"role": "user", "content": draw(_SAFE_TEXT)}],
        output_text=draw(_SAFE_TEXT),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_s=duration,
        estimated_cost_usd=cost,
        agent_name=agent_name,
        task_name=task_name,
        timestamp=timestamp,
    )


@st.composite
def llm_call_record_list_strategy(
    draw: st.DrawFn,
    min_size: int = 0,
    max_size: int = 5,
) -> list[LLMCallRecord]:
    """Generate a list of LLMCallRecord with non-decreasing timestamps."""
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    records: list[LLMCallRecord] = []
    ts = 0.0
    for _ in range(n):
        rec = draw(llm_call_record_strategy(min_timestamp=ts))
        records.append(rec)
        ts = rec.timestamp
    return records


# ---------------------------------------------------------------------------
# ToolCallRecord strategy
# ---------------------------------------------------------------------------


@st.composite
def tool_call_record_strategy(
    draw: st.DrawFn,
    min_timestamp: float = 0.0,
) -> ToolCallRecord:
    """Generate a valid ToolCallRecord."""
    tool_name = draw(_SAFE_TEXT)
    input_args = {draw(_SAFE_TEXT): draw(_SAFE_TEXT)}
    return_value = draw(_SAFE_TEXT)
    duration = draw(
        st.floats(
            min_value=0.0,
            max_value=1000.0,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    timestamp = draw(
        st.floats(
            min_value=min_timestamp,
            max_value=min_timestamp + 1000.0,
            allow_nan=False,
            allow_infinity=False,
        )
    )

    return ToolCallRecord(
        tool_name=tool_name,
        input_args=input_args,
        return_value=return_value,
        duration_s=duration,
        timestamp=timestamp,
    )


@st.composite
def tool_call_record_list_strategy(
    draw: st.DrawFn,
    min_size: int = 0,
    max_size: int = 5,
) -> list[ToolCallRecord]:
    """Generate a list of ToolCallRecord with non-decreasing timestamps."""
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    records: list[ToolCallRecord] = []
    ts = 0.0
    for _ in range(n):
        rec = draw(tool_call_record_strategy(min_timestamp=ts))
        records.append(rec)
        ts = rec.timestamp
    return records


# ---------------------------------------------------------------------------
# Trace strategy
# ---------------------------------------------------------------------------


@st.composite
def valid_trace_strategy(draw: st.DrawFn) -> Trace:
    """Generate a Trace with proper hierarchy and containment.

    Structure:
    - One crew root span
    - 1-5 task children
    - 0-3 llm_call and 0-3 tool_call leaves per task
    - Child time ranges are contained within parent time ranges
    - All span_ids are unique UUID4 strings
    """
    spans: list[Span] = []

    # Root crew span
    crew_id = str(uuid.uuid4())
    crew_start = draw(
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
    )
    crew_end = draw(
        st.floats(
            min_value=crew_start + 1.0,
            max_value=crew_start + 500.0,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    spans.append(
        Span(
            span_id=crew_id,
            parent_span_id=None,
            span_type=SpanType.crew,
            start_time=crew_start,
            end_time=crew_end,
            metadata={"run_id": str(uuid.uuid4())},
        )
    )

    # Task children
    num_tasks = draw(st.integers(min_value=1, max_value=5))
    task_duration = (crew_end - crew_start) / num_tasks

    for i in range(num_tasks):
        task_id = str(uuid.uuid4())
        task_start = crew_start + i * task_duration
        task_end = crew_start + (i + 1) * task_duration
        task_name = draw(_SAFE_TEXT)

        spans.append(
            Span(
                span_id=task_id,
                parent_span_id=crew_id,
                span_type=SpanType.task,
                start_time=task_start,
                end_time=task_end,
                metadata={"task_name": task_name},
            )
        )

        # LLM call leaves under this task
        num_llm = draw(st.integers(min_value=0, max_value=3))
        # Tool call leaves under this task
        num_tool = draw(st.integers(min_value=0, max_value=3))

        total_leaves = num_llm + num_tool
        if total_leaves > 0:
            leaf_duration = (task_end - task_start) / total_leaves
        else:
            leaf_duration = 0.0

        leaf_idx = 0
        for _ in range(num_llm):
            llm_id = str(uuid.uuid4())
            llm_start = task_start + leaf_idx * leaf_duration
            llm_end = task_start + (leaf_idx + 1) * leaf_duration
            model_id = draw(st.sampled_from(_MODEL_IDS))
            input_tokens = draw(st.integers(min_value=0, max_value=10000))
            output_tokens = draw(st.integers(min_value=0, max_value=10000))
            cost = estimate_cost(model_id, input_tokens, output_tokens)

            spans.append(
                Span(
                    span_id=llm_id,
                    parent_span_id=task_id,
                    span_type=SpanType.llm_call,
                    start_time=llm_start,
                    end_time=llm_end,
                    metadata={
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "estimated_cost_usd": cost,
                        "model_id": model_id,
                    },
                )
            )
            leaf_idx += 1

        for _ in range(num_tool):
            tool_id = str(uuid.uuid4())
            tool_start = task_start + leaf_idx * leaf_duration
            tool_end = task_start + (leaf_idx + 1) * leaf_duration

            spans.append(
                Span(
                    span_id=tool_id,
                    parent_span_id=task_id,
                    span_type=SpanType.tool_call,
                    start_time=tool_start,
                    end_time=tool_end,
                    metadata={
                        "tool_name": draw(_SAFE_TEXT),
                        "success": True,
                    },
                )
            )
            leaf_idx += 1

    return Trace(spans=spans)


# ---------------------------------------------------------------------------
# RunRecord strategy
# ---------------------------------------------------------------------------


@st.composite
def run_record_strategy(draw: st.DrawFn) -> RunRecord:
    """Compose sub-strategies into a valid RunRecord.

    Cost and latency summaries are computed from the generated data
    (not random) to maintain consistency.
    """
    manifest = draw(run_manifest_strategy())
    llm_calls = draw(llm_call_record_list_strategy(min_size=0, max_size=5))
    tool_calls = draw(tool_call_record_list_strategy(min_size=0, max_size=5))
    trace = draw(valid_trace_strategy())

    # Compute cost summary from llm_calls
    total_usd = 0.0
    per_agent: dict[str, float] = defaultdict(float)
    warnings: list[str] = []
    for call in llm_calls:
        if call.model_id not in MODEL_PRICING:
            warnings.append(
                f"Unknown model_id '{call.model_id}': cost recorded as 0.0"
            )
        total_usd += call.estimated_cost_usd
        per_agent[call.agent_name] += call.estimated_cost_usd

    cost_summary = CostSummary(
        total_usd=total_usd,
        per_agent=dict(per_agent),
        warnings=warnings,
    )

    # Compute latency summary from trace
    total_s = 0.0
    per_task: dict[str, float] = {}
    aggregate_llm_s = 0.0
    aggregate_tool_s = 0.0

    for span in trace.spans:
        duration = span.end_time - span.start_time
        if span.span_type == SpanType.crew:
            total_s = duration
        elif span.span_type == SpanType.task:
            task_name = span.metadata.get("task_name", span.span_id)
            per_task[task_name] = duration
        elif span.span_type == SpanType.llm_call:
            aggregate_llm_s += duration
        elif span.span_type == SpanType.tool_call:
            aggregate_tool_s += duration

    latency_summary = LatencySummary(
        total_s=total_s,
        per_task=per_task,
        aggregate_llm_s=aggregate_llm_s,
        aggregate_tool_s=aggregate_tool_s,
    )

    return RunRecord(
        run_id=str(uuid.uuid4()),
        manifest=manifest,
        prompt_snapshots=[],
        tool_calls=tool_calls,
        llm_calls=llm_calls,
        trace=trace,
        cost_summary=cost_summary,
        latency_summary=latency_summary,
        agent_outputs={},
        created_at=datetime.now(timezone.utc).isoformat(),
    )
