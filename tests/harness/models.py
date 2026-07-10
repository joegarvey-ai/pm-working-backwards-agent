"""Pydantic v2 data models for the agent harness.

Every model serialises to JSON via ``model_dump_json()`` and deserialises
via ``model_validate_json()`` without data loss.  Duration fields are
``float`` seconds (monotonic clock).  Datetime fields are ISO 8601 UTC
strings.
"""

from __future__ import annotations

import difflib
from enum import StrEnum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SpanType(StrEnum):
    """Span type discriminator for trace nodes."""

    crew = "crew"
    task = "task"
    llm_call = "llm_call"
    tool_call = "tool_call"


# ---------------------------------------------------------------------------
# Configuration snapshot
# ---------------------------------------------------------------------------


class RunManifest(BaseModel, frozen=True):
    """Frozen configuration snapshot captured at the start of a crew run.

    All hash fields are 64-character lowercase hexadecimal SHA-256 strings.
    """

    model_id: str
    agents_yaml_hash: str
    tasks_yaml_hash: str
    tool_names_by_agent: dict[str, list[str]]
    env_flags: dict[str, bool]
    input_brief_hash: str


# ---------------------------------------------------------------------------
# Prompt capture
# ---------------------------------------------------------------------------


class PromptSnapshot(BaseModel):
    """Captured prompt text for one agent/task pair after interpolation."""

    agent_role: str
    agent_goal: str
    agent_backstory: str
    task_description: str
    task_expected_output: str
    agent_name: str
    task_name: str
    sequence_index: int

    @classmethod
    def diff(cls, a: PromptSnapshot, b: PromptSnapshot) -> str:
        """Return a unified diff string between two snapshots.

        Compares the five prompt-text fields (role, goal, backstory,
        task_description, task_expected_output) and produces a unified
        diff suitable for human review.
        """
        fields = [
            "agent_role",
            "agent_goal",
            "agent_backstory",
            "task_description",
            "task_expected_output",
        ]
        lines_a: list[str] = []
        lines_b: list[str] = []
        for field in fields:
            lines_a.append(f"[{field}]")
            lines_a.append(getattr(a, field))
            lines_b.append(f"[{field}]")
            lines_b.append(getattr(b, field))

        return "\n".join(
            difflib.unified_diff(
                lines_a,
                lines_b,
                fromfile=f"{a.agent_name}/{a.task_name}",
                tofile=f"{b.agent_name}/{b.task_name}",
                lineterm="",
            )
        )


# ---------------------------------------------------------------------------
# Call records
# ---------------------------------------------------------------------------


class ToolCallRecord(BaseModel):
    """Single tool invocation record."""

    tool_name: str
    input_args: dict
    return_value: str
    duration_s: float
    error_class: str | None = None
    error_message: str | None = None
    timestamp: float  # monotonic


class LLMCallRecord(BaseModel):
    """Single LLM API call record."""

    model_id: str
    input_messages: list[dict[str, str]]
    output_text: str
    input_tokens: int
    output_tokens: int
    duration_s: float
    estimated_cost_usd: float
    agent_name: str
    task_name: str
    error_class: str | None = None
    error_message: str | None = None
    timestamp: float  # monotonic


# ---------------------------------------------------------------------------
# Trace
# ---------------------------------------------------------------------------


class Span(BaseModel):
    """Single trace node."""

    span_id: str  # UUID4
    parent_span_id: str | None = None
    span_type: SpanType
    start_time: float  # monotonic seconds
    end_time: float  # monotonic seconds
    metadata: dict = Field(default_factory=dict)


class Trace(BaseModel):
    """Collection of spans for a single crew run."""

    spans: list[Span] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------


class CostSummary(BaseModel):
    """Aggregated cost data for a crew run."""

    total_usd: float
    per_agent: dict[str, float]
    warnings: list[str] = Field(default_factory=list)


class LatencySummary(BaseModel):
    """Aggregated timing data for a crew run."""

    total_s: float
    per_task: dict[str, float]
    aggregate_llm_s: float
    aggregate_tool_s: float


# ---------------------------------------------------------------------------
# Top-level container
# ---------------------------------------------------------------------------


class CriterionScoreRecord(BaseModel):
    """One judge criterion score (1-5) with its rationale."""

    criterion: str
    score: int
    rationale: str = ""


class JudgeResultRecord(BaseModel):
    """Serializable result of one LLM-as-judge evaluation.

    ``error`` is populated when the judge call or response parse failed;
    in that case ``overall_score`` is meaningless and must not be read as
    a real low score. Consumers check ``error is None`` before trusting
    the scores.
    """

    judge_name: str
    scores: list[CriterionScoreRecord] = Field(default_factory=list)
    overall_score: float = 0.0
    summary: str = ""
    error: str | None = None


class RunRecord(BaseModel):
    """Top-level container for a single crew execution."""

    run_id: str  # UUID4
    manifest: RunManifest
    prompt_snapshots: list[PromptSnapshot] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    llm_calls: list[LLMCallRecord] = Field(default_factory=list)
    trace: Trace
    cost_summary: CostSummary
    latency_summary: LatencySummary
    agent_outputs: dict[str, str] = Field(default_factory=dict)
    judge_results: list[JudgeResultRecord] = Field(default_factory=list)
    created_at: str  # ISO 8601 UTC
