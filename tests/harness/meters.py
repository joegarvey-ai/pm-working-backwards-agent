"""Cost and latency meters for crew run analysis.

CostMeter aggregates estimated USD cost from LLM call records.
LatencyMeter extracts timing data from a structured Trace.
"""

from __future__ import annotations

from collections import defaultdict

from pm_agent_system.pricing import MODEL_PRICING

from .models import CostSummary, LatencySummary, LLMCallRecord, SpanType, Trace


class CostMeter:
    """Compute cost summaries from LLM call records."""

    @staticmethod
    def compute(llm_calls: list[LLMCallRecord]) -> CostSummary:
        """Sum ``estimated_cost_usd`` across all calls, grouped by agent.

        Records a warning for any call whose ``model_id`` is not found
        in :data:`MODEL_PRICING`.
        """
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

        return CostSummary(
            total_usd=total_usd,
            per_agent=dict(per_agent),
            warnings=warnings,
        )


class LatencyMeter:
    """Compute latency summaries from a structured Trace."""

    @staticmethod
    def compute(trace: Trace) -> LatencySummary:
        """Extract total, per-task, aggregate LLM, and aggregate tool durations."""
        total_s = 0.0
        per_task: dict[str, float] = {}
        aggregate_llm_s = 0.0
        aggregate_tool_s = 0.0

        for span in trace.spans:
            duration = span.end_time - span.start_time

            if span.span_type == SpanType.crew:
                total_s = duration
            elif span.span_type == SpanType.task:
                # Use task_name from metadata if available, fall back to span_id
                task_name = span.metadata.get("task_name", span.span_id)
                per_task[task_name] = duration
            elif span.span_type == SpanType.llm_call:
                aggregate_llm_s += duration
            elif span.span_type == SpanType.tool_call:
                aggregate_tool_s += duration

        return LatencySummary(
            total_s=total_s,
            per_task=per_task,
            aggregate_llm_s=aggregate_llm_s,
            aggregate_tool_s=aggregate_tool_s,
        )
