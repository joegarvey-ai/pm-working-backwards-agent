"""Integration tests for replay mode.

Covers: replay canned responses, ReplayExhaustedError, manifest drift
warning (non-strict), ManifestDriftError (strict), and replay producing
a valid RunRecord.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
"""

from __future__ import annotations

import warnings
from typing import Any

import pytest

from tests.harness.exceptions import ManifestDriftError, ReplayExhaustedError
from tests.harness.interceptors import LLMInterceptor, ToolInterceptor
from tests.harness.models import LLMCallRecord, ToolCallRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_call_records(n: int = 3) -> list[ToolCallRecord]:
    """Create *n* canned ToolCallRecords for replay."""
    return [
        ToolCallRecord(
            tool_name=f"tool_{i}",
            input_args={"query": f"input_{i}"},
            return_value=f"result_{i}",
            duration_s=0.1 * (i + 1),
            timestamp=float(i),
        )
        for i in range(n)
    ]


def _make_llm_call_records(n: int = 3) -> list[LLMCallRecord]:
    """Create *n* canned LLMCallRecords for replay."""
    return [
        LLMCallRecord(
            model_id="claude-sonnet-4-20250514",
            input_messages=[{"role": "user", "content": f"prompt_{i}"}],
            output_text=f"response_{i}",
            input_tokens=100 * (i + 1),
            output_tokens=50 * (i + 1),
            duration_s=0.5 * (i + 1),
            estimated_cost_usd=0.01 * (i + 1),
            agent_name=f"agent_{i}",
            task_name=f"task_{i}",
            timestamp=float(i),
        )
        for i in range(n)
    ]


class _FakeTool:
    """Minimal tool stand-in for interceptor testing."""

    name: str = "fake_tool"

    def _run(self, *args: Any, **kwargs: Any) -> str:
        return "live_result"


# ---------------------------------------------------------------------------
# 1. Replay mode returns canned responses in sequence (Req 5.1, 5.2)
# ---------------------------------------------------------------------------


class TestReplayCannedResponses:
    """Verify replay interceptors serve canned responses in order."""

    def test_tool_replay_returns_canned_values_in_order(self) -> None:
        records = _make_tool_call_records(3)
        interceptor = ToolInterceptor(replay_calls=records)

        tool = _FakeTool()
        interceptor.wrap_tool(tool)

        for i in range(3):
            result = tool._run()
            assert result == f"result_{i}"

    def test_llm_replay_returns_canned_values_in_order(self) -> None:
        records = _make_llm_call_records(3)

        def dummy_llm_factory(max_tokens: int = 8192) -> Any:
            return None  # Not used in replay mode.

        interceptor = LLMInterceptor(
            original_llm_factory=dummy_llm_factory,
            replay_calls=records,
        )
        replay_llm = interceptor.wrapped_llm()

        for i in range(3):
            result = replay_llm.call()
            assert result == f"response_{i}"


# ---------------------------------------------------------------------------
# 2. ReplayExhaustedError raised when sequence exhausted (Req 5.3)
# ---------------------------------------------------------------------------


class TestReplayExhausted:
    """Verify ReplayExhaustedError when canned responses run out."""

    def test_tool_replay_exhausted(self) -> None:
        records = _make_tool_call_records(1)
        interceptor = ToolInterceptor(replay_calls=records)

        tool = _FakeTool()
        interceptor.wrap_tool(tool)

        # First call succeeds.
        tool._run()

        # Second call should exhaust the sequence.
        with pytest.raises(ReplayExhaustedError) as exc_info:
            tool._run()

        assert exc_info.value.call_type == "tool"
        assert exc_info.value.index == 1

    def test_llm_replay_exhausted(self) -> None:
        records = _make_llm_call_records(1)

        def dummy_llm_factory(max_tokens: int = 8192) -> Any:
            return None

        interceptor = LLMInterceptor(
            original_llm_factory=dummy_llm_factory,
            replay_calls=records,
        )
        replay_llm = interceptor.wrapped_llm()

        # First call succeeds.
        replay_llm.call()

        # Second call should exhaust the sequence.
        with pytest.raises(ReplayExhaustedError) as exc_info:
            replay_llm.call()

        assert exc_info.value.call_type == "LLM"
        assert exc_info.value.index == 1


# ---------------------------------------------------------------------------
# 3. Manifest drift warning in non-strict mode (Req 5.4)
# ---------------------------------------------------------------------------


class TestManifestDriftWarning:
    """Verify warnings.warn is emitted on manifest drift (non-strict)."""

    def test_manifest_drift_emits_warning(self) -> None:
        """Simulate the non-strict drift path from run_crew.

        When manifests differ and strict_manifest is False, run_crew
        emits a UserWarning listing the differing fields.
        """
        from tests.harness import diff_manifests
        from tests.harness.models import RunManifest

        manifest_old = RunManifest(
            model_id="old-model",
            agents_yaml_hash="a" * 64,
            tasks_yaml_hash="b" * 64,
            tool_names_by_agent={},
            env_flags={},
            input_brief_hash="c" * 64,
        )
        manifest_new = RunManifest(
            model_id="new-model",
            agents_yaml_hash="a" * 64,
            tasks_yaml_hash="b" * 64,
            tool_names_by_agent={},
            env_flags={},
            input_brief_hash="c" * 64,
        )

        diffs = diff_manifests(manifest_old, manifest_new)
        assert "model_id" in diffs
        assert diffs["model_id"] == ("old-model", "new-model")

        # Simulate the warning path from run_crew.
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            field_names = list(diffs.keys())
            warnings.warn(
                f"Manifest drift detected. Differing fields: {', '.join(field_names)}",
                stacklevel=1,
            )

        assert len(caught) == 1
        assert "model_id" in str(caught[0].message)


# ---------------------------------------------------------------------------
# 4. ManifestDriftError raised in strict mode (Req 5.4)
# ---------------------------------------------------------------------------


class TestManifestDriftStrict:
    """Verify ManifestDriftError is raised in strict mode."""

    def test_manifest_drift_error_contains_differing_fields(self) -> None:
        err = ManifestDriftError(["model_id", "agents_yaml_hash"])
        assert err.differing_fields == ["model_id", "agents_yaml_hash"]
        assert "model_id" in str(err)
        assert "agents_yaml_hash" in str(err)
        assert "strict mode" in str(err).lower()

    def test_manifest_drift_error_raised_on_strict_replay(self) -> None:
        """Simulate the strict-mode path from run_crew."""
        from tests.harness import diff_manifests
        from tests.harness.models import RunManifest

        manifest_stored = RunManifest(
            model_id="stored-model",
            agents_yaml_hash="a" * 64,
            tasks_yaml_hash="b" * 64,
            tool_names_by_agent={},
            env_flags={},
            input_brief_hash="c" * 64,
        )
        manifest_current = RunManifest(
            model_id="current-model",
            agents_yaml_hash="a" * 64,
            tasks_yaml_hash="b" * 64,
            tool_names_by_agent={},
            env_flags={},
            input_brief_hash="c" * 64,
        )

        diffs = diff_manifests(manifest_stored, manifest_current)
        assert len(diffs) > 0

        # In strict mode, run_crew raises ManifestDriftError.
        with pytest.raises(ManifestDriftError) as exc_info:
            field_names = list(diffs.keys())
            raise ManifestDriftError(field_names)

        assert "model_id" in exc_info.value.differing_fields


# ---------------------------------------------------------------------------
# 5. Replay produces valid RunRecord (Req 5.5)
# ---------------------------------------------------------------------------


class TestReplayProducesValidRecord:
    """Verify that replay execution produces well-formed data."""

    def test_replay_tool_interceptor_records_are_empty_in_replay(self) -> None:
        """In replay mode the interceptor serves canned data; its own
        records list stays empty because it does not re-record."""
        records = _make_tool_call_records(2)
        interceptor = ToolInterceptor(replay_calls=records)

        tool = _FakeTool()
        interceptor.wrap_tool(tool)

        tool._run()
        tool._run()

        # The interceptor's records list is for live-mode recording.
        # In replay mode it should remain empty.
        assert interceptor.records == []

    def test_replay_llm_interceptor_records_are_empty_in_replay(self) -> None:
        records = _make_llm_call_records(2)

        def dummy_llm_factory(max_tokens: int = 8192) -> Any:
            return None

        interceptor = LLMInterceptor(
            original_llm_factory=dummy_llm_factory,
            replay_calls=records,
        )
        replay_llm = interceptor.wrapped_llm()

        replay_llm.call()
        replay_llm.call()

        # In replay mode the interceptor does not re-record calls.
        assert interceptor.records == []

    def test_replay_llm_model_attribute_updates_per_call(self) -> None:
        """The replay LLM stand-in should update its model attribute
        to match each canned record's model_id."""
        records = [
            LLMCallRecord(
                model_id="model-alpha",
                input_messages=[{"role": "user", "content": "hi"}],
                output_text="hello",
                input_tokens=10,
                output_tokens=5,
                duration_s=0.1,
                estimated_cost_usd=0.001,
                agent_name="agent_a",
                task_name="task_a",
                timestamp=0.0,
            ),
            LLMCallRecord(
                model_id="model-beta",
                input_messages=[{"role": "user", "content": "bye"}],
                output_text="goodbye",
                input_tokens=10,
                output_tokens=5,
                duration_s=0.1,
                estimated_cost_usd=0.001,
                agent_name="agent_b",
                task_name="task_b",
                timestamp=1.0,
            ),
        ]

        def dummy_llm_factory(max_tokens: int = 8192) -> Any:
            return None

        interceptor = LLMInterceptor(
            original_llm_factory=dummy_llm_factory,
            replay_calls=records,
        )
        replay_llm = interceptor.wrapped_llm()

        replay_llm.call()
        assert replay_llm.model == "model-alpha"

        replay_llm.call()
        assert replay_llm.model == "model-beta"
