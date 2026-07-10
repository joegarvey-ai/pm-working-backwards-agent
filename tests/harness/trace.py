"""Trace builder for structured span lifecycle management.

Manages a stack-based parent tracking system so that nested spans
(crew -> task -> llm_call / tool_call) automatically receive the correct
``parent_span_id``.
"""

from __future__ import annotations

import time
import uuid

from .models import Span, SpanType, Trace


class TraceBuilder:
    """Build a :class:`Trace` by starting and ending spans.

    Spans are pushed onto an internal stack so that each new span
    automatically inherits the current top-of-stack as its parent.
    """

    def __init__(self) -> None:
        self.spans: list[Span] = []
        self._stack: list[str] = []  # span_id stack for parent tracking

    def start_span(self, span_type: SpanType, metadata: dict | None = None) -> str:
        """Create and push a new span. Returns the generated ``span_id``."""
        span_id = str(uuid.uuid4())
        parent_span_id = self._stack[-1] if self._stack else None
        span = Span(
            span_id=span_id,
            parent_span_id=parent_span_id,
            span_type=span_type,
            start_time=time.perf_counter(),
            end_time=0.0,  # will be set in end_span
            metadata=metadata or {},
        )
        self.spans.append(span)
        self._stack.append(span_id)
        return span_id

    def end_span(self, span_id: str) -> None:
        """Set ``end_time`` on the span and pop it from the stack."""
        for span in self.spans:
            if span.span_id == span_id:
                span.end_time = time.perf_counter()
                break
        if self._stack and self._stack[-1] == span_id:
            self._stack.pop()

    def add_completed_span(
        self,
        span_type: SpanType,
        start_time: float,
        end_time: float,
        parent_span_id: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Record an already-finished span with explicit start/end times.

        Unlike ``start_span``/``end_span``, this does not touch the parent
        stack, so it is safe to call from the tool/LLM interceptors, which
        run concurrently under ``async_execution`` and record their own
        timing. The span is parented to ``parent_span_id`` (typically the
        root crew span) rather than to whatever happens to be on top of the
        stack at the time.
        """
        span_id = str(uuid.uuid4())
        parent = parent_span_id if parent_span_id is not None else (self._stack[-1] if self._stack else None)
        self.spans.append(
            Span(
                span_id=span_id,
                parent_span_id=parent,
                span_type=span_type,
                start_time=start_time,
                end_time=end_time,
                metadata=metadata or {},
            )
        )
        return span_id

    def build_trace(self) -> Trace:
        """Return the completed :class:`Trace`."""
        return Trace(spans=list(self.spans))
