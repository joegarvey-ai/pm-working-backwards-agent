"""Interceptors for recording and replaying tool and LLM calls.

``ToolInterceptor`` wraps CrewAI tool ``_run`` methods so every invocation
is timed, recorded as a :class:`~tests.harness.models.ToolCallRecord`, and
optionally replayed from a prior recording.

``LLMInterceptor`` wraps the ``_llm()`` factory from ``crew.py`` so every
LLM API call is timed, recorded as a
:class:`~tests.harness.models.LLMCallRecord`, and optionally replayed.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any

from pm_agent_system.pricing import estimate_cost

from .exceptions import ReplayExhaustedError
from .models import LLMCallRecord, ToolCallRecord


# ---------------------------------------------------------------------------
# ToolInterceptor
# ---------------------------------------------------------------------------


class ToolInterceptor:
    """Record or replay CrewAI tool invocations.

    Parameters
    ----------
    trace_builder:
        A :class:`TraceBuilder` instance for span integration (future use).
        May be ``None`` until the trace module is wired up.
    replay_calls:
        When provided, the interceptor operates in **replay mode** and
        serves canned responses from this list instead of calling the
        real tool.
    """

    def __init__(
        self,
        trace_builder: Any | None = None,
        replay_calls: list[ToolCallRecord] | None = None,
    ) -> None:
        self.records: list[ToolCallRecord] = []
        self._trace_builder = trace_builder
        self._replay_calls = replay_calls
        self._replay_index = 0

    # -- public API ---------------------------------------------------------

    def wrap_tool(self, tool: Any) -> None:
        """Replace *tool._run* with an intercepting wrapper.

        In **live mode** the wrapper calls the original ``_run``, records
        timing and results, and returns the original value (or re-raises
        the original exception).

        In **replay mode** the wrapper returns the next canned response
        from the stored :class:`ToolCallRecord` list, raising
        :class:`ReplayExhaustedError` when the sequence runs out.
        """
        original_run = tool._run

        @functools.wraps(original_run)
        def _intercepted_run(*args: Any, **kwargs: Any) -> str:
            if self._replay_calls is not None:
                return self._replay_tool_call(tool, args, kwargs)
            return self._live_tool_call(tool, original_run, args, kwargs)

        tool._run = _intercepted_run

    # -- internal helpers ---------------------------------------------------

    def _live_tool_call(
        self,
        tool: Any,
        original_run: Callable[..., str],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> str:
        """Execute the real tool and record the result."""
        tool_name = getattr(tool, "name", type(tool).__name__)
        input_args = _build_input_args(args, kwargs)

        start = time.perf_counter()
        error_class: str | None = None
        error_message: str | None = None
        return_value = ""

        try:
            return_value = original_run(*args, **kwargs)
            return return_value
        except Exception as exc:
            error_class = type(exc).__name__
            error_message = str(exc)
            raise
        finally:
            duration = time.perf_counter() - start
            record = ToolCallRecord(
                tool_name=tool_name,
                input_args=input_args,
                return_value=return_value,
                duration_s=duration,
                error_class=error_class,
                error_message=error_message,
                timestamp=start,
            )
            self.records.append(record)

    def _replay_tool_call(
        self,
        tool: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> str:
        """Return the next canned response from the replay sequence."""
        assert self._replay_calls is not None
        if self._replay_index >= len(self._replay_calls):
            raise ReplayExhaustedError("tool", self._replay_index)

        record = self._replay_calls[self._replay_index]
        self._replay_index += 1
        return record.return_value


# ---------------------------------------------------------------------------
# LLMInterceptor
# ---------------------------------------------------------------------------


class LLMInterceptor:
    """Record or replay LLM API calls.

    Parameters
    ----------
    original_llm_factory:
        The original ``_llm()`` factory callable from ``crew.py``.
    trace_builder:
        A :class:`TraceBuilder` instance for span integration (future use).
        May be ``None`` until the trace module is wired up.
    replay_calls:
        When provided, the interceptor operates in **replay mode** and
        serves canned responses from this list instead of calling the
        real LLM.
    """

    def __init__(
        self,
        original_llm_factory: Callable[..., Any],
        trace_builder: Any | None = None,
        replay_calls: list[LLMCallRecord] | None = None,
    ) -> None:
        self.records: list[LLMCallRecord] = []
        self._original_llm_factory = original_llm_factory
        self._trace_builder = trace_builder
        self._replay_calls = replay_calls
        self._replay_index = 0

    # -- public API ---------------------------------------------------------

    def wrapped_llm(self, max_tokens: int = 8192) -> Any:
        """Return an LLM instance that records or replays calls.

        In **live mode** the returned LLM's ``call`` method is wrapped so
        that every invocation is timed, token-counted, cost-estimated, and
        recorded as an :class:`LLMCallRecord`.

        In **replay mode** the returned object's ``call`` method returns
        the next canned response from the stored recording, raising
        :class:`ReplayExhaustedError` when the sequence runs out.
        """
        if self._replay_calls is not None:
            return self._build_replay_llm()

        return self._build_live_llm(max_tokens)

    # -- live mode ----------------------------------------------------------

    def _build_live_llm(self, max_tokens: int) -> Any:
        """Create a real LLM and wrap its ``call`` method."""
        llm = self._original_llm_factory(max_tokens=max_tokens)
        original_call = llm.call

        @functools.wraps(original_call)
        def _intercepted_call(
            messages: Any,
            *args: Any,
            from_task: Any | None = None,
            from_agent: Any | None = None,
            **kwargs: Any,
        ) -> Any:
            return self._live_llm_call(
                llm,
                original_call,
                messages,
                args,
                kwargs,
                from_task=from_task,
                from_agent=from_agent,
            )

        llm.call = _intercepted_call
        return llm

    def _live_llm_call(
        self,
        llm: Any,
        original_call: Callable[..., Any],
        messages: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        from_task: Any | None = None,
        from_agent: Any | None = None,
    ) -> Any:
        """Execute the real LLM call and record the result."""
        model_id = getattr(llm, "model", "unknown")

        # Snapshot token usage *before* the call so we can compute the delta.
        usage_before = _snapshot_token_usage(llm)

        start = time.perf_counter()
        error_class: str | None = None
        error_message: str | None = None
        output_text = ""
        input_tokens = 0
        output_tokens = 0

        try:
            result = original_call(
                messages,
                *args,
                from_task=from_task,
                from_agent=from_agent,
                **kwargs,
            )
            # The call method may return a string or a Pydantic model.
            output_text = str(result) if result is not None else ""

            # Compute token delta from the LLM's internal tracker.
            usage_after = _snapshot_token_usage(llm)
            input_tokens = usage_after["prompt_tokens"] - usage_before["prompt_tokens"]
            output_tokens = (
                usage_after["completion_tokens"] - usage_before["completion_tokens"]
            )

            return result
        except Exception as exc:
            error_class = type(exc).__name__
            error_message = str(exc)
            raise
        finally:
            duration = time.perf_counter() - start
            cost = estimate_cost(model_id, input_tokens, output_tokens)

            # Derive agent/task names from CrewAI objects when available.
            agent_name = _extract_name(from_agent, "agent")
            task_name = _extract_name(from_task, "task")

            record = LLMCallRecord(
                model_id=model_id,
                input_messages=_normalise_messages(messages),
                output_text=output_text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_s=duration,
                estimated_cost_usd=cost,
                agent_name=agent_name,
                task_name=task_name,
                error_class=error_class,
                error_message=error_message,
                timestamp=start,
            )
            self.records.append(record)

    # -- replay mode --------------------------------------------------------

    def _build_replay_llm(self) -> "_ReplayLLM":
        """Return a lightweight stand-in that replays canned responses."""
        return _ReplayLLM(self)


# ---------------------------------------------------------------------------
# Replay LLM stand-in
# ---------------------------------------------------------------------------


class _ReplayLLM:
    """Minimal LLM stand-in used during replay mode.

    Exposes a ``call`` method that returns the next recorded response text.
    Also exposes ``model`` and ``get_token_usage_summary`` so that
    downstream code that inspects the LLM object does not break.
    """

    def __init__(self, interceptor: LLMInterceptor) -> None:
        self._interceptor = interceptor
        # Set a sensible default model; will be overridden per-call.
        self.model = "replay"

    def call(
        self,
        messages: Any = None,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Return the next canned LLM response."""
        idx = self._interceptor._replay_index
        replay_calls = self._interceptor._replay_calls
        assert replay_calls is not None

        if idx >= len(replay_calls):
            raise ReplayExhaustedError("LLM", idx)

        record = replay_calls[idx]
        self._interceptor._replay_index += 1
        self.model = record.model_id
        return record.output_text

    def get_token_usage_summary(self) -> Any:
        """Return a no-op usage summary for compatibility."""
        return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_input_args(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Merge positional and keyword arguments into a JSON-friendly dict."""
    result: dict[str, Any] = {}
    if args:
        result["args"] = [str(a) for a in args]
    if kwargs:
        result.update({k: _safe_serialise(v) for k, v in kwargs.items()})
    return result


def _safe_serialise(value: Any) -> Any:
    """Best-effort conversion to a JSON-serialisable value."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, dict):
        return {k: _safe_serialise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_serialise(v) for v in value]
    return str(value)


def _snapshot_token_usage(llm: Any) -> dict[str, int]:
    """Return a copy of the LLM's internal token-usage counters."""
    try:
        usage = llm._token_usage
        return {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
        }
    except AttributeError:
        return {"prompt_tokens": 0, "completion_tokens": 0}


def _normalise_messages(messages: Any) -> list[dict[str, str]]:
    """Convert *messages* to a ``list[dict[str, str]]`` for recording.

    CrewAI may pass messages as a plain string, a list of dicts, or a
    list of ``LLMMessage`` objects.  We normalise to the simplest form.
    """
    if isinstance(messages, str):
        return [{"role": "user", "content": messages}]
    if isinstance(messages, list):
        result: list[dict[str, str]] = []
        for msg in messages:
            if isinstance(msg, dict):
                result.append(
                    {
                        "role": str(msg.get("role", "unknown")),
                        "content": str(msg.get("content", "")),
                    }
                )
            else:
                # LLMMessage or similar object with role/content attrs.
                result.append(
                    {
                        "role": str(getattr(msg, "role", "unknown")),
                        "content": str(getattr(msg, "content", "")),
                    }
                )
        return result
    return [{"role": "unknown", "content": str(messages)}]


def _extract_name(obj: Any, fallback_prefix: str) -> str:
    """Extract a human-readable name from a CrewAI Agent or Task object."""
    if obj is None:
        return f"unknown_{fallback_prefix}"
    # CrewAI Agent has .role; Task has .description (or .name if set).
    for attr in ("name", "role", "description"):
        val = getattr(obj, attr, None)
        if val and isinstance(val, str):
            return val
    return f"unknown_{fallback_prefix}"
