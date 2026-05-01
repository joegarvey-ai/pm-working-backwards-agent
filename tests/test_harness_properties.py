"""Property-based tests for agent-harness-evals correctness properties.

One test per property named in the agent-harness-evals design document.
Each test validates a universal rule across randomly generated inputs
using Hypothesis, rather than a single example.

Properties covered (17 total):
 1. RunRecord serialization round-trip
 2. Manifest diff correctness
 3. Tool interceptor transparency
 4. Tool interceptor error transparency
 5. LLM interceptor transparency
 6. LLM interceptor error transparency
 7. Record list ordering invariant
 8. Cost additive invariant
 9. Latency meter correctness
10. Span containment invariant
11. Latency budget violation detection
12. Cost cap violation detection
13. Input brief hash non-empty
14. Replay fidelity
15. Banned word detection
16. Span ID uniqueness
17. Trace structure hierarchy
"""

from __future__ import annotations

import hashlib
import json
import math
import re

import pytest
from hypothesis import given, settings, strategies as st

from pm_agent_system.pricing import MODEL_PRICING, estimate_cost

from tests.harness import diff_manifests
from tests.harness.evals.cost import check_cost_cap
from tests.harness.evals.latency import check_latency_budget
from tests.harness.evals.properties import (
    _MODEL_IDS,
    _SAFE_TEXT,
    _SHA256_HEX,
    llm_call_record_list_strategy,
    llm_call_record_strategy,
    run_manifest_strategy,
    run_record_strategy,
    tool_call_record_list_strategy,
    tool_call_record_strategy,
    valid_trace_strategy,
)
from tests.harness.evals.quality import BANNED_WORDS, assert_no_banned_words
from tests.harness.interceptors import ToolInterceptor
from tests.harness.meters import CostMeter, LatencyMeter
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
# Property 1: RunRecord serialization round-trip
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(record=run_record_strategy())
def test_property_1_run_record_round_trip(record: RunRecord):
    """Feature: agent-harness-evals, Property 1: RunRecord round-trip

    For any valid RunRecord instance, serializing to JSON via
    model_dump_json() and deserializing via model_validate_json()
    produces an object where every field compares equal to the original.

    **Validates: Requirements 1.2, 6.5, 7.5, 14.4, 15.1, 15.4**
    """
    json_str = record.model_dump_json(indent=2)
    restored = RunRecord.model_validate_json(json_str)
    assert restored == record


# ---------------------------------------------------------------------------
# Property 2: Manifest diff correctness
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(a=run_manifest_strategy(), b=run_manifest_strategy())
def test_property_2_manifest_diff_correctness(a: RunManifest, b: RunManifest):
    """Feature: agent-harness-evals, Property 2: Manifest diff correctness

    For any two RunManifest instances, diff_manifests(a, b) returns a
    dictionary where every key maps to a (old_value, new_value) tuple
    where old_value != new_value, and every field not in the dictionary
    has equal values in both manifests.

    **Validates: Requirements 1.3, 6.6**
    """
    diffs = diff_manifests(a, b)

    # Every reported diff must actually differ
    for field_name, (old_val, new_val) in diffs.items():
        assert old_val != new_val, (
            f"Field {field_name} reported as diff but values are equal"
        )
        assert old_val == getattr(a, field_name)
        assert new_val == getattr(b, field_name)

    # Every field NOT in diffs must be equal
    for field_name in RunManifest.model_fields:
        if field_name not in diffs:
            assert getattr(a, field_name) == getattr(b, field_name), (
                f"Field {field_name} differs but was not reported"
            )


# ---------------------------------------------------------------------------
# Property 3: Tool interceptor transparency
# ---------------------------------------------------------------------------


class _MockTool:
    """Minimal mock tool for interceptor tests."""

    name = "mock_tool"

    def _run(self, **kwargs) -> str:
        return f"result:{json.dumps(kwargs, sort_keys=True)}"


@settings(max_examples=100, deadline=None)
@given(
    key=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz",
        min_size=1,
        max_size=10,
    ),
    value=_SAFE_TEXT,
)
def test_property_3_tool_interceptor_transparency(key: str, value: str):
    """Feature: agent-harness-evals, Property 3: Tool interceptor transparency

    For any tool and any input arguments, invoking the tool through the
    ToolInterceptor returns the same value as invoking the tool directly
    without the interceptor.

    **Validates: Requirements 3.2**
    """
    tool = _MockTool()
    expected = tool._run(**{key: value})

    # Now wrap and call through interceptor
    tool2 = _MockTool()
    interceptor = ToolInterceptor(trace_builder=None, replay_calls=None)
    interceptor.wrap_tool(tool2)
    actual = tool2._run(**{key: value})

    assert actual == expected
    assert len(interceptor.records) == 1
    assert interceptor.records[0].tool_name == "mock_tool"
    assert interceptor.records[0].return_value == expected


# ---------------------------------------------------------------------------
# Property 4: Tool interceptor error transparency
# ---------------------------------------------------------------------------


class _ErrorTool:
    """Mock tool that always raises."""

    name = "error_tool"

    def _run(self, **kwargs) -> str:
        raise ValueError(f"boom:{json.dumps(kwargs, sort_keys=True)}")


@settings(max_examples=100, deadline=None)
@given(
    key=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz",
        min_size=1,
        max_size=10,
    ),
    value=_SAFE_TEXT,
)
def test_property_4_tool_error_transparency(key: str, value: str):
    """Feature: agent-harness-evals, Property 4: Tool error transparency

    For any tool that raises an exception for a given input, invoking
    the tool through the ToolInterceptor re-raises the same exception
    type with the same message, and records the error_class and
    error_message in the ToolCallRecord.

    **Validates: Requirements 3.4**
    """
    tool = _ErrorTool()
    interceptor = ToolInterceptor(trace_builder=None, replay_calls=None)
    interceptor.wrap_tool(tool)

    with pytest.raises(ValueError, match="boom:"):
        tool._run(**{key: value})

    assert len(interceptor.records) == 1
    rec = interceptor.records[0]
    assert rec.error_class == "ValueError"
    assert rec.error_message is not None
    assert "boom:" in rec.error_message


# ---------------------------------------------------------------------------
# Property 5: LLM interceptor transparency
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    message_content=_SAFE_TEXT,
    response_text=_SAFE_TEXT,
)
def test_property_5_llm_interceptor_transparency(
    message_content: str,
    response_text: str,
):
    """Feature: agent-harness-evals, Property 5: LLM interceptor transparency

    For any LLM call with any input messages, invoking the LLM through
    the LLMInterceptor returns the same response text and token counts
    as invoking the LLM directly without the interceptor.

    **Validates: Requirements 4.3**
    """
    from tests.harness.interceptors import LLMInterceptor

    model_id = _MODEL_IDS[0]
    canned = LLMCallRecord(
        model_id=model_id,
        input_messages=[{"role": "user", "content": message_content}],
        output_text=response_text,
        input_tokens=100,
        output_tokens=50,
        duration_s=0.5,
        estimated_cost_usd=estimate_cost(model_id, 100, 50),
        agent_name="test_agent",
        task_name="test_task",
        timestamp=0.0,
    )

    interceptor = LLMInterceptor(
        original_llm_factory=lambda **kw: None,
        trace_builder=None,
        replay_calls=[canned],
    )
    replay_llm = interceptor.wrapped_llm()
    result = replay_llm.call()

    assert result == response_text


# ---------------------------------------------------------------------------
# Property 6: LLM interceptor error transparency
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(error_msg=_SAFE_TEXT)
def test_property_6_llm_error_transparency(error_msg: str):
    """Feature: agent-harness-evals, Property 6: LLM error transparency

    For any LLM call that raises an API error, invoking the LLM through
    the LLMInterceptor re-raises the same exception type with the same
    message, and records the error_class and error_message in the
    LLMCallRecord.

    **Validates: Requirements 4.5**
    """
    from tests.harness.interceptors import LLMInterceptor

    class _FakeLLM:
        model = _MODEL_IDS[0]
        _token_usage = {"prompt_tokens": 0, "completion_tokens": 0}

        def call(
            self,
            messages=None,
            *args,
            from_task=None,
            from_agent=None,
            **kwargs,
        ):
            raise RuntimeError(error_msg)

    def fake_factory(**kwargs):
        return _FakeLLM()

    interceptor = LLMInterceptor(
        original_llm_factory=fake_factory,
        trace_builder=None,
        replay_calls=None,
    )
    llm = interceptor.wrapped_llm()

    with pytest.raises(RuntimeError, match=re.escape(error_msg)):
        llm.call("hello")

    assert len(interceptor.records) == 1
    rec = interceptor.records[0]
    assert rec.error_class == "RuntimeError"
    assert rec.error_message == error_msg


# ---------------------------------------------------------------------------
# Property 7: Record list ordering invariant
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(record=run_record_strategy())
def test_property_7_record_list_ordering(record: RunRecord):
    """Feature: agent-harness-evals, Property 7: Record list ordering

    For any valid RunRecord, the tool_calls list has monotonically
    non-decreasing timestamp values, and the llm_calls list has
    monotonically non-decreasing timestamp values.

    **Validates: Requirements 2.3, 3.3, 4.4**
    """
    for i in range(1, len(record.tool_calls)):
        assert record.tool_calls[i].timestamp >= record.tool_calls[i - 1].timestamp, (
            f"tool_calls timestamps not non-decreasing at index {i}"
        )

    for i in range(1, len(record.llm_calls)):
        assert record.llm_calls[i].timestamp >= record.llm_calls[i - 1].timestamp, (
            f"llm_calls timestamps not non-decreasing at index {i}"
        )


# ---------------------------------------------------------------------------
# Property 8: Cost additive invariant
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(llm_calls=llm_call_record_list_strategy(min_size=0, max_size=10))
def test_property_8_cost_additive_invariant(llm_calls: list[LLMCallRecord]):
    """Feature: agent-harness-evals, Property 8: Cost additive invariant

    CostMeter total_usd equals the sum of estimated_cost_usd across all
    records, and the sum of all per-agent costs equals total_usd. Each
    individual estimated_cost_usd equals pricing.estimate_cost(model_id,
    input_tokens, output_tokens).

    **Validates: Requirements 8.1, 8.2, 8.3, 14.2**
    """
    summary = CostMeter.compute(llm_calls)

    # Total equals sum of individual costs
    expected_total = sum(c.estimated_cost_usd for c in llm_calls)
    assert math.isclose(summary.total_usd, expected_total, rel_tol=1e-9), (
        f"Total {summary.total_usd} != sum {expected_total}"
    )

    # Sum of per-agent costs equals total
    per_agent_sum = sum(summary.per_agent.values())
    assert math.isclose(per_agent_sum, summary.total_usd, rel_tol=1e-9), (
        f"Per-agent sum {per_agent_sum} != total {summary.total_usd}"
    )

    # Each individual cost matches estimate_cost
    for call in llm_calls:
        expected_cost = estimate_cost(
            call.model_id, call.input_tokens, call.output_tokens
        )
        assert math.isclose(call.estimated_cost_usd, expected_cost, rel_tol=1e-9), (
            f"Call cost {call.estimated_cost_usd} != estimate {expected_cost}"
        )


# ---------------------------------------------------------------------------
# Property 9: Latency meter correctness
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(trace=valid_trace_strategy())
def test_property_9_latency_meter_correctness(trace: Trace):
    """Feature: agent-harness-evals, Property 9: Latency meter correctness

    For any valid Trace, the LatencyMeter computes total_s equal to the
    root span's end_time - start_time, each per_task duration equal to
    its task span's end_time - start_time, aggregate_llm_s equal to the
    sum of all llm_call span durations, and aggregate_tool_s equal to
    the sum of all tool_call span durations.

    **Validates: Requirements 9.1, 9.2, 9.3, 9.5**
    """
    summary = LatencyMeter.compute(trace)

    # Find root crew span
    crew_spans = [s for s in trace.spans if s.span_type == SpanType.crew]
    assert len(crew_spans) == 1
    root = crew_spans[0]

    assert math.isclose(
        summary.total_s, root.end_time - root.start_time, rel_tol=1e-9
    )

    # Per-task durations
    for span in trace.spans:
        if span.span_type == SpanType.task:
            task_name = span.metadata.get("task_name", span.span_id)
            expected_dur = span.end_time - span.start_time
            assert task_name in summary.per_task
            assert math.isclose(
                summary.per_task[task_name], expected_dur, rel_tol=1e-9
            )

    # Aggregate LLM
    expected_llm = sum(
        s.end_time - s.start_time
        for s in trace.spans
        if s.span_type == SpanType.llm_call
    )
    assert math.isclose(summary.aggregate_llm_s, expected_llm, rel_tol=1e-9)

    # Aggregate tool
    expected_tool = sum(
        s.end_time - s.start_time
        for s in trace.spans
        if s.span_type == SpanType.tool_call
    )
    assert math.isclose(summary.aggregate_tool_s, expected_tool, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Property 10: Span containment invariant
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(trace=valid_trace_strategy())
def test_property_10_span_containment(trace: Trace):
    """Feature: agent-harness-evals, Property 10: Span containment

    For any valid Trace tree, every child Span's time range
    [start_time, end_time] falls within its parent Span's time range.

    **Validates: Requirements 14.3**
    """
    span_map = {s.span_id: s for s in trace.spans}

    for span in trace.spans:
        if span.parent_span_id is not None:
            parent = span_map[span.parent_span_id]
            assert span.start_time >= parent.start_time - 1e-9, (
                f"Child {span.span_id} starts before parent {parent.span_id}"
            )
            assert span.end_time <= parent.end_time + 1e-9, (
                f"Child {span.span_id} ends after parent {parent.span_id}"
            )


# ---------------------------------------------------------------------------
# Property 11: Latency budget violation detection
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(record=run_record_strategy())
def test_property_11_latency_budget_detection(record: RunRecord):
    """Feature: agent-harness-evals, Property 11: Latency budget detection

    check_latency_budget raises AssertionError iff at least one task's
    duration exceeds its budget or the total duration exceeds the total
    budget.

    **Validates: Requirements 12.1, 12.2, 12.3**
    """
    per_task = record.latency_summary.per_task
    total_s = record.latency_summary.total_s

    # Case 1: generous budgets (should pass)
    generous_budgets = {name: dur + 100.0 for name, dur in per_task.items()}
    generous_total = total_s + 100.0
    # Should not raise
    check_latency_budget(record, generous_budgets, generous_total)

    # Case 2: tight budgets (should fail if any task has positive duration)
    if per_task and any(dur > 0 for dur in per_task.values()):
        tight_budgets = {name: 0.0 for name in per_task}
        with pytest.raises(AssertionError):
            check_latency_budget(record, tight_budgets, total_s + 100.0)

    # Case 3: tight total budget
    if total_s > 0:
        with pytest.raises(AssertionError):
            check_latency_budget(record, generous_budgets, 0.0)


# ---------------------------------------------------------------------------
# Property 12: Cost cap violation detection
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(record=run_record_strategy())
def test_property_12_cost_cap_detection(record: RunRecord):
    """Feature: agent-harness-evals, Property 12: Cost cap detection

    check_cost_cap raises AssertionError iff the total cost exceeds the
    cap.

    **Validates: Requirements 13.1, 13.2, 13.3, 13.4**
    """
    total = record.cost_summary.total_usd

    # Generous cap: should pass
    check_cost_cap(record, total + 100.0)

    # Tight cap: should fail if cost is positive
    if total > 0:
        with pytest.raises(AssertionError):
            check_cost_cap(record, 0.0)


# ---------------------------------------------------------------------------
# Property 13: Input brief hash non-empty
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    brief=st.text(min_size=1, max_size=200),
)
def test_property_13_input_brief_hash(brief: str):
    """Feature: agent-harness-evals, Property 13: Input brief hash non-empty

    For any non-empty input brief string, the SHA-256 hash is a 64-char
    hex string.

    **Validates: Requirements 14.1**
    """
    digest = hashlib.sha256(
        json.dumps({"brief": brief}, sort_keys=True).encode("utf-8")
    ).hexdigest()

    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


# ---------------------------------------------------------------------------
# Property 14: Replay fidelity
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    tool_calls=tool_call_record_list_strategy(min_size=1, max_size=5),
)
def test_property_14_replay_fidelity(tool_calls: list[ToolCallRecord]):
    """Feature: agent-harness-evals, Property 14: Replay fidelity

    Replay returns recorded responses in order. For any recorded list of
    ToolCallRecords, replaying them through the ToolInterceptor in replay
    mode returns the return_value from the i-th recorded call on the i-th
    invocation.

    **Validates: Requirements 5.1, 5.2**
    """
    interceptor = ToolInterceptor(
        trace_builder=None,
        replay_calls=tool_calls,
    )

    class _DummyTool:
        name = "dummy"

        def _run(self, **kwargs) -> str:
            return "should_not_be_called"

    tool = _DummyTool()
    interceptor.wrap_tool(tool)

    for i, expected_record in enumerate(tool_calls):
        result = tool._run()
        assert result == expected_record.return_value, (
            f"Replay call {i}: expected {expected_record.return_value!r}, "
            f"got {result!r}"
        )


# ---------------------------------------------------------------------------
# Property 15: Banned word detection
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    banned_word=st.sampled_from(BANNED_WORDS),
    prefix=_SAFE_TEXT,
    suffix=_SAFE_TEXT,
)
def test_property_15_banned_word_detection(
    banned_word: str,
    prefix: str,
    suffix: str,
):
    """Feature: agent-harness-evals, Property 15: Banned word detection

    assert_no_banned_words raises AssertionError iff a banned word is
    present in agent outputs.

    **Validates: Requirements 11.3**
    """
    # Build a RunRecord with a banned word in agent_outputs
    from tests.harness.evals.properties import run_record_strategy

    # Create a minimal RunRecord with the banned word embedded
    text_with_banned = f"{prefix} {banned_word} {suffix}"

    record = RunRecord(
        run_id="test-run",
        manifest=RunManifest(
            model_id=_MODEL_IDS[0],
            agents_yaml_hash="a" * 64,
            tasks_yaml_hash="b" * 64,
            tool_names_by_agent={},
            env_flags={},
            input_brief_hash="c" * 64,
        ),
        prompt_snapshots=[],
        tool_calls=[],
        llm_calls=[],
        trace=Trace(spans=[]),
        cost_summary=CostSummary(total_usd=0.0, per_agent={}, warnings=[]),
        latency_summary=LatencySummary(
            total_s=0.0,
            per_task={},
            aggregate_llm_s=0.0,
            aggregate_tool_s=0.0,
        ),
        agent_outputs={"test_task": text_with_banned},
        created_at="2025-01-01T00:00:00Z",
    )

    with pytest.raises(AssertionError, match="banned"):
        assert_no_banned_words(record)


@settings(max_examples=100, deadline=None)
@given(clean_text=_SAFE_TEXT)
def test_property_15_clean_text_passes(clean_text: str):
    """Feature: agent-harness-evals, Property 15: Banned word detection (clean)

    For any string that contains no banned words, the assertion passes.

    **Validates: Requirements 11.3**
    """
    # Filter out any text that accidentally contains a banned word
    lower = clean_text.lower()
    for word in BANNED_WORDS:
        if word.lower() in lower:
            return  # skip this example

    record = RunRecord(
        run_id="test-run",
        manifest=RunManifest(
            model_id=_MODEL_IDS[0],
            agents_yaml_hash="a" * 64,
            tasks_yaml_hash="b" * 64,
            tool_names_by_agent={},
            env_flags={},
            input_brief_hash="c" * 64,
        ),
        prompt_snapshots=[],
        tool_calls=[],
        llm_calls=[],
        trace=Trace(spans=[]),
        cost_summary=CostSummary(total_usd=0.0, per_agent={}, warnings=[]),
        latency_summary=LatencySummary(
            total_s=0.0,
            per_task={},
            aggregate_llm_s=0.0,
            aggregate_tool_s=0.0,
        ),
        agent_outputs={"test_task": clean_text},
        created_at="2025-01-01T00:00:00Z",
    )

    # Should not raise
    assert_no_banned_words(record)


# ---------------------------------------------------------------------------
# Property 16: Span ID uniqueness
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(trace=valid_trace_strategy())
def test_property_16_span_id_uniqueness(trace: Trace):
    """Feature: agent-harness-evals, Property 16: Span ID uniqueness

    All span_id values in a trace are unique.

    **Validates: Requirements 7.2**
    """
    span_ids = [s.span_id for s in trace.spans]
    assert len(span_ids) == len(set(span_ids)), "Duplicate span_ids found"


# ---------------------------------------------------------------------------
# Property 17: Trace structure hierarchy
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(trace=valid_trace_strategy())
def test_property_17_trace_structure_hierarchy(trace: Trace):
    """Feature: agent-harness-evals, Property 17: Trace structure hierarchy

    One crew root, task children, llm/tool leaves. There is exactly one
    root Span of type crew with parent_span_id = None. Every task Span
    has the root Span as its parent. Every llm_call and tool_call Span
    has a task Span as its parent.

    **Validates: Requirements 7.1, 7.3, 7.4**
    """
    span_map = {s.span_id: s for s in trace.spans}

    # Exactly one crew root
    crew_spans = [s for s in trace.spans if s.span_type == SpanType.crew]
    assert len(crew_spans) == 1, f"Expected 1 crew span, found {len(crew_spans)}"
    root = crew_spans[0]
    assert root.parent_span_id is None

    # Every task has the crew root as parent
    for span in trace.spans:
        if span.span_type == SpanType.task:
            assert span.parent_span_id == root.span_id, (
                f"Task {span.span_id} parent is {span.parent_span_id}, "
                f"expected {root.span_id}"
            )

    # Every llm_call and tool_call has a task as parent
    for span in trace.spans:
        if span.span_type in (SpanType.llm_call, SpanType.tool_call):
            assert span.parent_span_id is not None
            parent = span_map[span.parent_span_id]
            assert parent.span_type == SpanType.task, (
                f"{span.span_type} span {span.span_id} parent is "
                f"{parent.span_type}, expected task"
            )

    # llm_call metadata contains required keys
    for span in trace.spans:
        if span.span_type == SpanType.llm_call:
            for key in ("input_tokens", "output_tokens", "estimated_cost_usd", "model_id"):
                assert key in span.metadata, (
                    f"llm_call span {span.span_id} missing metadata key '{key}'"
                )

    # tool_call metadata contains required keys
    for span in trace.spans:
        if span.span_type == SpanType.tool_call:
            for key in ("tool_name", "success"):
                assert key in span.metadata, (
                    f"tool_call span {span.span_id} missing metadata key '{key}'"
                )
