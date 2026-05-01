# Implementation Plan: Agent Harness Evals

## Overview

This plan implements a test harness, observability layer, and evaluation framework for the PM Working Backwards multi-agent CrewAI system. The implementation follows the three-phase structure from the design: Harness (data models, interceptors, entry point), Observability (traces, meters, logging), and Evals (quality assertions, budget checks, property tests). All code lives in `tests/harness/` as a Python module and builds on existing infrastructure (`pricing.py`, `checkpoint.py`, Pydantic models).

## Tasks

- [x] 1. Set up harness module structure and data models
  - [x] 1.1 Create `tests/harness/` package with `__init__.py`, `models.py`, `exceptions.py`
    - Create directory structure: `tests/harness/`, `tests/harness/evals/`
    - Define custom exceptions in `exceptions.py`: `HarnessConfigError`, `ReplayExhaustedError`, `ManifestDriftError`
    - Stub `__init__.py` with placeholder imports
    - _Requirements: 1.4, 5.3, 5.4_

  - [x] 1.2 Implement all Pydantic data models in `tests/harness/models.py`
    - Define `SpanType` enum (crew, task, llm_call, tool_call)
    - Define `RunManifest` model with model_id, agents_yaml_hash, tasks_yaml_hash, tool_names_by_agent, env_flags, input_brief_hash
    - Define `PromptSnapshot` model with agent_role, agent_goal, agent_backstory, task_description, task_expected_output, agent_name, task_name, sequence_index
    - Define `ToolCallRecord` model with tool_name, input_args, return_value, duration_s, error_class, error_message, timestamp
    - Define `LLMCallRecord` model with model_id, input_messages, output_text, input_tokens, output_tokens, duration_s, estimated_cost_usd, agent_name, task_name, error_class, error_message, timestamp
    - Define `Span` model with span_id, parent_span_id, span_type, start_time, end_time, metadata
    - Define `Trace` model with spans list
    - Define `CostSummary` model with total_usd, per_agent, warnings
    - Define `LatencySummary` model with total_s, per_task, aggregate_llm_s, aggregate_tool_s
    - Define `RunRecord` model with run_id, manifest, prompt_snapshots, tool_calls, llm_calls, trace, cost_summary, latency_summary, agent_outputs, created_at
    - _Requirements: 1.2, 2.1, 3.1, 4.1, 7.2, 7.3, 7.4, 8.4, 9.4, 15.1, 15.2, 15.3_

  - [ ]* 1.3 Write property test for RunRecord serialization round-trip
    - **Property 1: RunRecord serialization round-trip**
    - **Validates: Requirements 1.2, 6.5, 7.5, 14.4, 15.1, 15.4**

  - [ ]* 1.4 Write unit tests for data models
    - Test JSON serialization with 2-space indentation (Req 15.3)
    - Test ISO 8601 datetime format and float duration fields (Req 15.2)
    - Test prompt snapshot diff generation (Req 2.4)
    - _Requirements: 15.2, 15.3, 2.4_

- [x] 2. Implement interceptors
  - [x] 2.1 Implement `ToolInterceptor` in `tests/harness/interceptors.py`
    - Create `ToolInterceptor` class with `wrap_tool` method that replaces `tool._run` with an intercepting wrapper
    - In live mode: call real tool, record ToolCallRecord with tool_name, input_args, return_value, duration_s, timestamp
    - On exception: record error_class and error_message, then re-raise unchanged
    - In replay mode: return next canned response from stored ToolCallRecords
    - Raise `ReplayExhaustedError` when replay sequence is exhausted
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 5.2, 5.3_

  - [ ]* 2.2 Write property test for tool interceptor transparency
    - **Property 3: Tool interceptor transparency**
    - **Validates: Requirements 3.2**

  - [ ]* 2.3 Write property test for tool interceptor error transparency
    - **Property 4: Tool interceptor error transparency**
    - **Validates: Requirements 3.4**

  - [x] 2.4 Implement `LLMInterceptor` in `tests/harness/interceptors.py`
    - Create `LLMInterceptor` class with `wrapped_llm` method that wraps the `_llm()` factory
    - In live mode: call real LLM, record LLMCallRecord with model_id, input_messages, output_text, input_tokens, output_tokens, duration_s, estimated_cost_usd (via `pricing.estimate_cost`), agent_name, task_name, timestamp
    - On exception: record error_class and error_message, then re-raise unchanged
    - In replay mode: return next canned response from stored LLMCallRecords
    - Raise `ReplayExhaustedError` when replay sequence is exhausted
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.3_

  - [ ]* 2.5 Write property test for LLM interceptor transparency
    - **Property 5: LLM interceptor transparency**
    - **Validates: Requirements 4.3**

  - [ ]* 2.6 Write property test for LLM interceptor error transparency
    - **Property 6: LLM interceptor error transparency**
    - **Validates: Requirements 4.5**

  - [ ]* 2.7 Write property test for record list ordering invariant
    - **Property 7: Record list ordering invariant**
    - **Validates: Requirements 2.3, 3.3, 4.4**

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement trace builder and meters
  - [x] 4.1 Implement `TraceBuilder` in `tests/harness/trace.py`
    - Create `TraceBuilder` class with span stack for parent tracking
    - Implement `start_span(span_type, metadata)` that creates a Span with UUID4 span_id, sets parent_span_id from stack, records start_time
    - Implement `end_span(span_id)` that sets end_time and pops from stack
    - Implement `build_trace()` that returns the completed Trace
    - Ensure span_id uniqueness via UUID4 generation
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 4.2 Write property test for span containment invariant
    - **Property 10: Span containment invariant**
    - **Validates: Requirements 14.3**

  - [ ]* 4.3 Write property test for span ID uniqueness
    - **Property 16: Span ID uniqueness**
    - **Validates: Requirements 7.2**

  - [ ]* 4.4 Write property test for trace structure hierarchy
    - **Property 17: Trace structure hierarchy**
    - **Validates: Requirements 7.1, 7.3, 7.4**

  - [x] 4.5 Implement `CostMeter` in `tests/harness/meters.py`
    - Create `CostMeter` class with static `compute(llm_calls)` method
    - Sum `estimated_cost_usd` across all LLMCallRecords for total_usd
    - Group by agent_name for per_agent breakdown
    - Record warning for any call where model_id is not in `MODEL_PRICING`
    - Use `pricing.estimate_cost` for consistency
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 4.6 Write property test for cost additive invariant
    - **Property 8: Cost additive invariant**
    - **Validates: Requirements 8.1, 8.2, 8.3, 14.2**

  - [x] 4.7 Implement `LatencyMeter` in `tests/harness/meters.py`
    - Create `LatencyMeter` class with static `compute(trace)` method
    - Compute total_s from root span's end_time - start_time
    - Compute per_task from each task span's duration
    - Compute aggregate_llm_s from sum of all llm_call span durations
    - Compute aggregate_tool_s from sum of all tool_call span durations
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 4.8 Write property test for latency meter correctness
    - **Property 9: Latency meter correctness**
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.5**

- [x] 5. Implement structured logging
  - [x] 5.1 Implement `emit_event` in `tests/harness/logging.py`
    - Create dedicated `harness` logger via `logging.getLogger("harness")`
    - Implement `emit_event(event_type, span_id, run_id, **kwargs)` that emits INFO-level log records
    - Include structured fields in `extra` dict: event_type, span_id, run_id, plus event-specific fields (tool_name, model, tokens_in, tokens_out, duration_s, cost_usd)
    - Support event types: crew_start, crew_end, task_start, task_end, llm_call_start, llm_call_end, tool_call_start, tool_call_end
    - Do not add file handlers by default
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ]* 5.2 Write unit tests for structured logging
    - Test log event emission with correct event_type and structured fields
    - Test logger name is "harness"
    - Test no file handlers attached by default
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 6. Implement harness entry point API
  - [x] 6.1 Implement `run_crew` function in `tests/harness/__init__.py`
    - Accept Crew object, inputs dict, optional replay_path, optional output_path, optional strict_manifest flag
    - Capture RunManifest (model_id, SHA-256 hashes of agents.yaml/tasks.yaml, tool names per agent, env flags, input brief hash)
    - Raise `HarnessConfigError` if agents.yaml or tasks.yaml cannot be read
    - Wire up LLMInterceptor, ToolInterceptor, TraceBuilder, and HarnessLogger
    - Execute crew.kickoff(inputs) with full interception
    - Assemble RunRecord with all captured data, CostSummary, LatencySummary
    - Write RunRecord to output_path if provided (2-space indented JSON)
    - _Requirements: 1.1, 1.4, 6.1, 6.2, 6.4_

  - [x] 6.2 Implement replay mode in `run_crew`
    - When replay_path is provided, load stored RunRecord
    - Compare manifests: warn on drift (non-strict), raise ManifestDriftError (strict)
    - Initialize LLMInterceptor and ToolInterceptor in replay mode with stored call records
    - Produce a new RunRecord from the replay execution
    - _Requirements: 5.1, 5.2, 5.4, 5.5, 6.3_

  - [x] 6.3 Implement `load_record` and `diff_manifests` functions
    - `load_record(path)`: Read JSON file, validate with `RunRecord.model_validate_json()`, return model
    - `diff_manifests(a, b)`: Compare two RunManifests field-by-field, return dict of differing fields with (old, new) tuples
    - _Requirements: 6.5, 6.6, 1.3_

  - [ ]* 6.4 Write property test for manifest diff correctness
    - **Property 2: Manifest diff correctness**
    - **Validates: Requirements 1.3, 6.6**

  - [ ]* 6.5 Write property test for input brief hash non-empty
    - **Property 13: Input brief hash is non-empty**
    - **Validates: Requirements 14.1**

  - [ ]* 6.6 Write property test for replay fidelity
    - **Property 14: Replay fidelity**
    - **Validates: Requirements 5.1, 5.2**

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement eval assertion functions
  - [x] 8.1 Implement output quality evals in `tests/harness/evals/quality.py`
    - Create `tests/harness/evals/__init__.py`
    - Implement `assert_schema_valid(record)`: Validate each agent output against its Pydantic schema (ResearchOutput, PRFAQOutput, BRDOutput, CodingPromptOutput)
    - Implement `assert_min_content(record)`: Check ResearchOutput has source with URL, PRFAQOutput has press_release, BRDOutput has functional_requirement, CodingPromptOutput has formatted_spec
    - Implement `assert_no_banned_words(record)`: Scan outputs for banned words list
    - Each function accepts RunRecord, raises AssertionError with descriptive message on failure
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [ ]* 8.2 Write property test for banned word detection
    - **Property 15: Banned word detection**
    - **Validates: Requirements 11.3**

  - [x] 8.3 Implement latency budget evals in `tests/harness/evals/latency.py`
    - Implement `check_latency_budget(record, budgets, total_budget)`: Check per-task and total durations against budgets
    - Raise AssertionError listing each task that exceeded, with budget and actual values
    - Raise AssertionError if task name in budget dict not found in trace
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

  - [ ]* 8.4 Write property test for latency budget violation detection
    - **Property 11: Latency budget violation detection**
    - **Validates: Requirements 12.1, 12.2, 12.3**

  - [x] 8.5 Implement cost cap evals in `tests/harness/evals/cost.py`
    - Implement `check_cost_cap(record, max_cost_usd)`: Raise AssertionError if total cost exceeds cap
    - Implement `check_per_agent_cost_cap(record, caps)`: Raise AssertionError listing each agent that exceeded its cap
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [ ]* 8.6 Write property test for cost cap violation detection
    - **Property 12: Cost cap violation detection**
    - **Validates: Requirements 13.1, 13.2, 13.3, 13.4**

- [x] 9. Implement Hypothesis property test module
  - [x] 9.1 Create custom Hypothesis strategies in `tests/harness/evals/properties.py`
    - Implement `run_manifest_strategy()`: Generate RunManifest with random model IDs, SHA-256 hex strings, tool name lists, env flag dicts
    - Implement `llm_call_record_strategy()`: Generate LLMCallRecord with model IDs from MODEL_PRICING keys, random token counts (0-10000), costs via `pricing.estimate_cost`
    - Implement `tool_call_record_strategy()`: Generate ToolCallRecord with random tool names, input dicts, return values, durations
    - Implement `valid_trace_strategy()`: Generate Trace with proper hierarchy (one crew root, N task children, M llm_call/tool_call leaves per task) and valid containment
    - Implement `run_record_strategy()`: Compose all sub-strategies into a valid RunRecord with consistent cost and latency summaries
    - Use `@st.composite` decorators, `_SAFE_TEXT` alphabet restrictions, `@settings(max_examples=100, deadline=None)`
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

  - [x] 9.2 Create `tests/test_harness_properties.py` test runner
    - Import all property test functions from `tests/harness/evals/properties.py`
    - Wire up all 17 property tests as pytest-discoverable test functions
    - Each test function includes docstring: `Feature: agent-harness-evals, Property N: {property_text}`
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

- [x] 10. Integration tests and final wiring
  - [x] 10.1 Create integration test file `tests/test_harness_api.py`
    - Test `run_crew` function signature and return type
    - Test `HarnessConfigError` raised when config files missing
    - Test `load_record` reads and validates JSON correctly
    - Test `diff_manifests` returns correct diff dictionary
    - Test output_path writing produces valid JSON with 2-space indentation
    - _Requirements: 1.4, 6.1, 6.4, 6.5, 6.6_

  - [x] 10.2 Create replay integration test file `tests/test_harness_replay.py`
    - Test replay mode returns canned responses in sequence
    - Test `ReplayExhaustedError` raised when sequence exhausted
    - Test manifest drift warning in non-strict mode
    - Test `ManifestDriftError` raised in strict mode
    - Test replay produces valid RunRecord
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 10.3 Write unit tests for eval assertion functions in `tests/test_harness_evals.py`
    - Test `assert_schema_valid` with valid and invalid outputs
    - Test `assert_min_content` with missing content
    - Test `assert_no_banned_words` with banned and clean text
    - Test `check_latency_budget` with exceeded and passing budgets
    - Test `check_latency_budget` with missing task name
    - Test `check_cost_cap` with exceeded and passing caps
    - Test `check_per_agent_cost_cap` with exceeded and passing caps
    - _Requirements: 11.2, 11.4, 12.4, 13.1, 13.4_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate the 17 universal correctness properties from the design
- Unit tests validate specific examples and edge cases
- All code lives in `tests/harness/` with no production code changes required
- The implementation uses Python 3.11+, Pydantic v2, pytest, and Hypothesis (all already in `pyproject.toml`)
