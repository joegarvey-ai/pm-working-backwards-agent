"""Tests for the LLM-as-judge evals without hitting a live API.

Monkeypatches judge._call_judge so the judge logic (parsing, scoring,
error handling) is exercised deterministically.
"""

from __future__ import annotations

import json

import pytest

from tests.harness.evals import judge
from tests.harness.models import (
    CostSummary,
    LatencySummary,
    RunManifest,
    RunRecord,
    Trace,
)


def _make_record(agent_outputs: dict[str, str]) -> RunRecord:
    return RunRecord(
        run_id="test-run",
        manifest=RunManifest(
            model_id="claude-haiku-4-5",
            agents_yaml_hash="0",
            tasks_yaml_hash="0",
            tool_names_by_agent={},
            env_flags={},
            input_brief_hash="0",
        ),
        trace=Trace(spans=[]),
        cost_summary=CostSummary(total_usd=0.0, per_agent={}, warnings=[]),
        latency_summary=LatencySummary(
            total_s=0.0, per_task={}, aggregate_llm_s=0.0, aggregate_tool_s=0.0
        ),
        agent_outputs=agent_outputs,
        created_at="2026-07-09T00:00:00+00:00",
    )


def _scores_json(score: int) -> str:
    return json.dumps(
        [
            {"criterion": "no_em_dashes", "score": score, "rationale": "r"},
            {"criterion": "no_contrast_hooks", "score": score, "rationale": "r"},
            {"criterion": "inline_citations", "score": score, "rationale": "r"},
        ]
    )


def test_good_prfaq_scores_high(monkeypatch):
    monkeypatch.setattr(judge, "_call_judge", lambda s, u: _scores_json(5))
    result = judge.judge_prfaq_fidelity(_make_record({"generate_prfaq": "a clean prfaq"}))
    assert result.error is None
    assert result.overall_score >= 4.0


def test_bad_prfaq_scores_low(monkeypatch):
    monkeypatch.setattr(judge, "_call_judge", lambda s, u: _scores_json(2))
    result = judge.judge_prfaq_fidelity(_make_record({"generate_prfaq": "em dash - riddled"}))
    assert result.error is None
    assert result.overall_score < 3.0


def test_parse_failure_is_not_a_zero_score(monkeypatch):
    # A judge that returns unparseable text must set error, NOT report 0.0
    # as if it were a real (failing) score.
    monkeypatch.setattr(judge, "_call_judge", lambda s, u: "the model rambled, no JSON here")
    result = judge.judge_prfaq_fidelity(_make_record({"generate_prfaq": "x"}))
    assert result.error == "parse_failed"
    assert not result.scores


def test_call_failure_is_captured(monkeypatch):
    def _boom(s, u):
        raise RuntimeError("no credentials")

    monkeypatch.setattr(judge, "_call_judge", _boom)
    result = judge.judge_prfaq_fidelity(_make_record({"generate_prfaq": "x"}))
    assert result.error is not None
    assert "call_failed" in result.error


def test_missing_artifact_returns_neutral(monkeypatch):
    # No PRFAQ in the record: neutral result, no judge call made.
    called = False

    def _tracker(s, u):
        nonlocal called
        called = True
        return _scores_json(5)

    monkeypatch.setattr(judge, "_call_judge", _tracker)
    result = judge.judge_prfaq_fidelity(_make_record({}))
    assert not called
    assert "No PRFAQ" in result.summary


def test_to_record_round_trips(monkeypatch):
    monkeypatch.setattr(judge, "_call_judge", lambda s, u: _scores_json(4))
    result = judge.judge_prfaq_fidelity(_make_record({"generate_prfaq": "x"}))
    rec = result.to_record()
    # Serializes cleanly for storage on the RunRecord.
    dumped = rec.model_dump_json()
    assert "prfaq_fidelity" in dumped
    assert rec.error is None
    assert len(rec.scores) == 3
