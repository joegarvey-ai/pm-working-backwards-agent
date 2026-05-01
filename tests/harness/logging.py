"""Structured logging for the agent harness."""

from __future__ import annotations

import logging

# Dedicated logger for harness events. No handlers attached by default;
# log routing is the caller's responsibility.
_logger = logging.getLogger("harness")


def emit_event(
    event_type: str,
    span_id: str,
    run_id: str,
    **kwargs: object,
) -> None:
    """Emit a structured log record at INFO level on the 'harness' logger.

    Parameters
    ----------
    event_type:
        One of: crew_start, crew_end, task_start, task_end,
        llm_call_start, llm_call_end, tool_call_start, tool_call_end.
    span_id:
        The span_id associated with this event.
    run_id:
        The run_id for the current crew execution.
    **kwargs:
        Event-specific fields (e.g., tool_name, model, tokens_in,
        tokens_out, duration_s, cost_usd).
    """
    extra = {
        "event_type": event_type,
        "span_id": span_id,
        "run_id": run_id,
        **kwargs,
    }
    _logger.info(
        "%s [run=%s span=%s]",
        event_type,
        run_id,
        span_id,
        extra=extra,
    )
