# Requirements Document

## Introduction

This feature adds a test harness, observability layer, and evaluation framework to the PM Working Backwards multi-agent CrewAI system. The goal is to make agent runs reproducible, measurable, and assertable so that prompt changes, model upgrades, and tool additions can be validated before they reach production.

The work is sequenced in three phases:

1. **Harness** (`tests/harness/`): Wraps crew execution with prompt snapshot capture, tool call recording, LLM call interception for replay and mocking, and run manifests that freeze configuration for reproducible execution.
2. **Observability**: Instruments the harness with structured traces, per-call cost and latency metering, and structured logs that feed both human review and automated evaluation.
3. **Evals**: Assertions on output quality, latency budgets, cost caps, and correctness properties that run as standard pytest tests against recorded or live runs.

All three phases build on the existing project infrastructure: `pytest` and `hypothesis` for testing, the `pricing.py` module for cost estimation, the `checkpoint.py` manifest for run state, and the `VaultCheckpointProvider` pattern for intercepting crew execution. No new external dependencies are introduced beyond what is already in `pyproject.toml`.

## Glossary

- **Harness**: The `tests/harness/` Python module that wraps CrewAI crew execution to capture prompts, tool calls, LLM requests/responses, and configuration into a structured run record.
- **Run_Record**: A JSON-serializable data structure produced by the Harness for a single crew execution. Contains the run manifest, prompt snapshots, tool call log, LLM call log, agent outputs, and timing data.
- **Run_Manifest**: A frozen snapshot of all configuration that affects a crew run: model identifier, agent YAML, task YAML, environment flags, tool list per agent, and input brief hash. Used to detect configuration drift between runs.
- **Prompt_Snapshot**: A captured copy of the system prompt, agent backstory, and task description text that was sent to the LLM for a given agent during a run. Stored inside the Run_Record.
- **Tool_Call_Record**: A single entry in the tool call log capturing the tool name, input arguments, output value, duration, and any error that occurred.
- **LLM_Call_Record**: A single entry in the LLM call log capturing the model identifier, input messages, output text, token counts (input and output), latency, and estimated cost.
- **LLM_Interceptor**: A wrapper around the CrewAI LLM provider that records every LLM call and optionally replays canned responses from a prior Run_Record instead of calling the real API.
- **Tool_Interceptor**: A wrapper around CrewAI tool execution that records every tool call and optionally returns canned responses from a prior Run_Record.
- **Replay_Mode**: A Harness execution mode where LLM and tool calls are served from a previously recorded Run_Record instead of calling live APIs. Enables deterministic, zero-cost test execution.
- **Trace**: A structured record of a crew run organized as a tree of spans: one root span per crew execution, child spans per task, and leaf spans per LLM call and tool call. Each span carries timing, token counts, and cost.
- **Span**: A single node in a Trace tree. Has a type (crew, task, llm_call, tool_call), a start time, an end time, and type-specific metadata.
- **Cost_Meter**: A component that accumulates estimated USD cost across all LLM calls in a run using the token counts from LLM_Call_Records and the rates from `pricing.py`.
- **Latency_Meter**: A component that records wall-clock duration for each span in a Trace and computes aggregate statistics (total, per-task, per-agent, p50, p95).
- **Eval**: A pytest test function that loads a Run_Record (from replay or live execution) and asserts properties about the outputs, cost, latency, or trace structure.
- **Eval_Suite**: A collection of Eval functions grouped by concern (output quality, cost, latency, correctness).
- **PmAgentSystem**: The existing CrewAI crew orchestrator class in `src/pm_agent_system/crew.py`.
- **CrewAI_Tool**: A Python class extending `crewai.tools.BaseTool` with a name, description, args_schema, and `_run` method.
- **Pipeline**: The full agent sequence: Research Agent, PRFAQ Agent, BRD Agent, Build Spec.

## Scope Summary

- **Phase 1 (Harness)**: Requirements 1 through 6 cover the run manifest, prompt snapshot capture, tool call recording, LLM call interception, replay mode, and the harness entry point API.
- **Phase 2 (Observability)**: Requirements 7 through 10 cover structured traces, cost metering, latency metering, and structured logging.
- **Phase 3 (Evals)**: Requirements 11 through 14 cover output quality assertions, latency budget assertions, cost cap assertions, and correctness property tests.
- **Cross-cutting**: Requirement 15 covers serialization round-trip for all harness data structures.

## Requirements

### Requirement 1: Run Manifest Capture

**User Story:** As an engineer, I want every crew run to produce a frozen manifest of its configuration, so that I can detect when a prompt change, model swap, or tool addition caused a regression.

#### Acceptance Criteria

1. WHEN a crew execution starts through the Harness, THE Harness SHALL capture a Run_Manifest containing: the model identifier string, the SHA-256 hash of `agents.yaml` content, the SHA-256 hash of `tasks.yaml` content, the list of tool class names attached to each agent, the set of environment flag keys that affect crew behavior (LLM_PROVIDER, DOVETAIL_API_TOKEN presence, BUILDER_MCP_TOKEN presence, OUTLOOK_MCP_TOKEN presence), and the SHA-256 hash of the input brief content.
2. THE Run_Manifest SHALL be a Pydantic model defined in `tests/harness/models.py` and SHALL serialize to JSON and deserialize back without data loss.
3. WHEN two Run_Manifests are compared, THE Harness SHALL report which fields differ, so that a test can assert that a replay uses the same configuration as the original recording.
4. IF the `agents.yaml` or `tasks.yaml` file cannot be read at capture time, THEN THE Harness SHALL raise a `HarnessConfigError` with a message naming the missing file.

### Requirement 2: Prompt Snapshot Capture

**User Story:** As an engineer, I want to capture the exact prompt text sent to the LLM for each agent, so that I can diff prompts across runs and detect unintended prompt regressions.

#### Acceptance Criteria

1. WHEN the Harness wraps a crew execution, THE Harness SHALL capture one Prompt_Snapshot per agent per task, containing the agent role, goal, and backstory strings, the interpolated task description, and the interpolated task expected_output.
2. THE Prompt_Snapshot SHALL be captured after CrewAI interpolates `{variable}` placeholders with runtime input values, so that the snapshot reflects the actual text sent to the LLM.
3. THE Prompt_Snapshot SHALL be stored as a list inside the Run_Record, ordered by execution sequence.
4. WHEN two Prompt_Snapshots for the same agent and task are compared, THE Harness SHALL produce a unified diff string showing the text differences.

### Requirement 3: Tool Call Recording

**User Story:** As an engineer, I want every tool invocation during a crew run to be recorded with its inputs, outputs, and timing, so that I can verify tool behavior and replay tool responses in tests.

#### Acceptance Criteria

1. WHEN a CrewAI_Tool `_run` method is invoked during a harnessed crew execution, THE Tool_Interceptor SHALL record a Tool_Call_Record containing: the tool class name, the input arguments as a JSON-serializable dictionary, the return value as a string, the wall-clock duration in seconds, and any exception class name and message if the call raised.
2. THE Tool_Interceptor SHALL not alter the tool's return value or exception behavior. The crew execution SHALL produce identical results whether the Tool_Interceptor is active or not.
3. THE Tool_Call_Records SHALL be stored as a list inside the Run_Record, ordered by invocation time.
4. IF a tool call raises an exception, THEN THE Tool_Interceptor SHALL record the exception details in the Tool_Call_Record and re-raise the original exception unchanged.

### Requirement 4: LLM Call Interception

**User Story:** As an engineer, I want every LLM API call during a crew run to be recorded with its messages, token counts, and timing, so that I can compute cost, measure latency, and replay responses without calling the real API.

#### Acceptance Criteria

1. WHEN an LLM call is made during a harnessed crew execution, THE LLM_Interceptor SHALL record an LLM_Call_Record containing: the model identifier, the input messages (system and user), the output text, the input token count, the output token count, the wall-clock duration in seconds, and the estimated cost in USD computed via `pricing.estimate_cost`.
2. THE LLM_Interceptor SHALL wrap the existing `_llm()` factory function in `crew.py` so that the interception applies to all agents without modifying individual agent definitions.
3. THE LLM_Interceptor SHALL not alter the LLM response content or token counts. The crew execution SHALL produce identical results whether the LLM_Interceptor is active or not.
4. THE LLM_Call_Records SHALL be stored as a list inside the Run_Record, ordered by invocation time.
5. IF an LLM call fails with an API error, THEN THE LLM_Interceptor SHALL record the error class name and message in the LLM_Call_Record and re-raise the original exception unchanged.

### Requirement 5: Replay Mode

**User Story:** As an engineer, I want to replay a previously recorded crew run using canned LLM and tool responses, so that I can run evaluations deterministically without incurring API costs.

#### Acceptance Criteria

1. WHEN the Harness is initialized in Replay_Mode with a path to a stored Run_Record JSON file, THE LLM_Interceptor SHALL return the recorded LLM response for each call in sequence instead of calling the real API.
2. WHEN the Harness is initialized in Replay_Mode, THE Tool_Interceptor SHALL return the recorded tool response for each call in sequence instead of calling the real tool.
3. IF the replay sequence is exhausted before the crew execution completes (more calls than recorded), THEN THE Harness SHALL raise a `ReplayExhaustedError` naming the call type (LLM or tool) and the index at which exhaustion occurred.
4. IF the Run_Manifest of the stored Run_Record differs from the current configuration, THEN THE Harness SHALL emit a warning listing the differing fields, but SHALL proceed with replay unless the caller sets `strict_manifest=True`, in which case THE Harness SHALL raise a `ManifestDriftError`.
5. WHEN a replay completes, THE Harness SHALL produce a new Run_Record that contains the replayed outputs and timing, so that evals can run against the replay record identically to a live record.

### Requirement 6: Harness Entry Point API

**User Story:** As an engineer, I want a simple Python API to run a crew through the harness, so that I can use it in pytest fixtures and CI scripts without boilerplate.

#### Acceptance Criteria

1. THE Harness SHALL expose a `run_crew` function in `tests/harness/__init__.py` that accepts a CrewAI `Crew` object, a dictionary of inputs, and an optional `replay_path` string, and returns a `Run_Record`.
2. WHEN `replay_path` is None, THE `run_crew` function SHALL execute the crew against live APIs with full interception and return a Run_Record containing all captured data.
3. WHEN `replay_path` is a valid file path, THE `run_crew` function SHALL execute the crew in Replay_Mode using the stored Run_Record at that path.
4. THE `run_crew` function SHALL accept an optional `output_path` string. WHEN provided, THE function SHALL write the Run_Record to that path as formatted JSON.
5. THE Harness SHALL expose a `load_record` function that reads a Run_Record JSON file from disk and returns a validated `Run_Record` Pydantic model.
6. THE Harness SHALL expose a `diff_manifests` function that accepts two Run_Manifests and returns a dictionary of field names to `(old_value, new_value)` tuples for all fields that differ.

### Requirement 7: Structured Trace Construction

**User Story:** As an engineer, I want each crew run to produce a structured trace tree, so that I can visualize the execution flow and identify which task or LLM call consumed the most time or tokens.

#### Acceptance Criteria

1. WHEN a harnessed crew execution completes, THE Harness SHALL produce a Trace containing a root Span of type `crew`, child Spans of type `task` (one per task executed), and leaf Spans of type `llm_call` and `tool_call` nested under their parent task Span.
2. EACH Span SHALL contain: a unique span_id string, a parent_span_id string (None for the root), a span_type enum value, a start_time float (monotonic seconds), an end_time float (monotonic seconds), and a metadata dictionary with type-specific fields.
3. THE `llm_call` Span metadata SHALL include input_tokens, output_tokens, estimated_cost_usd, and model identifier.
4. THE `tool_call` Span metadata SHALL include tool_name, success boolean, and error message if applicable.
5. THE Trace SHALL be stored inside the Run_Record and SHALL serialize to JSON and deserialize back without data loss.

### Requirement 8: Cost Metering

**User Story:** As an engineer, I want to know the total and per-agent estimated cost of a crew run, so that I can set cost budgets and detect cost regressions from prompt or model changes.

#### Acceptance Criteria

1. WHEN a harnessed crew execution completes, THE Cost_Meter SHALL compute the total estimated cost in USD by summing the `estimated_cost_usd` field from all LLM_Call_Records in the Run_Record.
2. THE Cost_Meter SHALL compute per-agent cost by grouping LLM_Call_Records by the agent name associated with each call.
3. THE Cost_Meter SHALL use the `pricing.estimate_cost` function with the model identifier and token counts from each LLM_Call_Record, so that cost estimation stays consistent with the existing pricing module.
4. THE cost summary (total and per-agent breakdown) SHALL be stored as a `cost_summary` field on the Run_Record.
5. IF the model identifier is not found in `pricing.MODEL_PRICING`, THEN THE Cost_Meter SHALL record a cost of 0.0 for that call and include a warning string in the cost summary.

### Requirement 9: Latency Metering

**User Story:** As an engineer, I want to know the wall-clock time for each phase of a crew run, so that I can set latency budgets and detect performance regressions.

#### Acceptance Criteria

1. WHEN a harnessed crew execution completes, THE Latency_Meter SHALL compute the total wall-clock duration in seconds from the root Span of the Trace.
2. THE Latency_Meter SHALL compute per-task duration from each task Span in the Trace.
3. THE Latency_Meter SHALL compute aggregate LLM latency (sum of all `llm_call` Span durations) and aggregate tool latency (sum of all `tool_call` Span durations).
4. THE latency summary (total, per-task, aggregate LLM, aggregate tool) SHALL be stored as a `latency_summary` field on the Run_Record.
5. WHILE async tasks execute in parallel (e.g., `external_research_task` and `customer_evidence_task`), THE Latency_Meter SHALL record each task's individual wall-clock duration independently, and the parent task Span SHALL reflect the wall-clock time from the first child start to the last child end.

### Requirement 10: Structured Logging

**User Story:** As an engineer, I want harness events emitted as structured log records, so that I can filter and search run history without parsing free-text logs.

#### Acceptance Criteria

1. THE Harness SHALL emit Python `logging` records at INFO level for: crew run start, crew run end, task start, task end, LLM call start, LLM call end, tool call start, and tool call end.
2. EACH log record SHALL include structured fields via the `extra` dictionary: `event_type` (string enum), `span_id`, `run_id`, and event-specific fields (e.g., `tool_name`, `model`, `tokens_in`, `tokens_out`, `duration_s`, `cost_usd`).
3. THE Harness SHALL use a dedicated logger named `harness` so that log filtering does not interfere with the existing `pm_agent_system` logger hierarchy.
4. THE Harness SHALL not write log output to files by default. Log routing is the caller's responsibility via standard Python logging configuration.

### Requirement 11: Output Quality Eval Assertions

**User Story:** As an engineer, I want to assert structural and content properties of agent outputs, so that I can catch quality regressions from prompt changes.

#### Acceptance Criteria

1. THE Eval_Suite SHALL include assertion functions that accept a Run_Record and verify that each agent's Pydantic output is present and validates against its schema (ResearchOutput, PRFAQOutput, BRDOutput, CodingPromptOutput).
2. THE Eval_Suite SHALL include assertion functions that verify ResearchOutput contains at least one source with a non-empty URL, PRFAQOutput contains a non-empty press_release field, BRDOutput contains at least one functional_requirement, and CodingPromptOutput contains a non-empty formatted_spec field.
3. THE Eval_Suite SHALL include assertion functions that verify no agent output contains any word from the project's banned word list (the list defined in agent backstories: "robust", "comprehensive", "powerful", "cutting-edge", "transformative", "game-changing", "revolutionary", "best-in-class", "seamless").
4. EACH assertion function SHALL accept a Run_Record as its sole required argument and SHALL raise `AssertionError` with a descriptive message on failure, so that it integrates with pytest's standard assertion reporting.

### Requirement 12: Latency Budget Eval Assertions

**User Story:** As an engineer, I want to set per-task and total latency budgets and fail a test when a run exceeds them, so that I can prevent latency regressions.

#### Acceptance Criteria

1. THE Eval_Suite SHALL include a `check_latency_budget` function that accepts a Run_Record and a budget dictionary mapping task names to maximum allowed duration in seconds, and a total maximum duration in seconds.
2. WHEN any task's duration exceeds its budget, THE function SHALL raise `AssertionError` listing each task that exceeded its budget, the budget value, and the actual duration.
3. WHEN the total run duration exceeds the total budget, THE function SHALL raise `AssertionError` with the budget value and the actual total duration.
4. IF a task name in the budget dictionary does not appear in the Run_Record's trace, THEN THE function SHALL raise `AssertionError` naming the missing task.

### Requirement 13: Cost Cap Eval Assertions

**User Story:** As an engineer, I want to set a cost cap for a crew run and fail a test when the run exceeds it, so that I can prevent cost regressions from prompt bloat or model changes.

#### Acceptance Criteria

1. THE Eval_Suite SHALL include a `check_cost_cap` function that accepts a Run_Record and a maximum allowed cost in USD.
2. WHEN the total estimated cost in the Run_Record's cost_summary exceeds the cap, THE function SHALL raise `AssertionError` with the cap value and the actual cost.
3. THE Eval_Suite SHALL include a `check_per_agent_cost_cap` function that accepts a Run_Record and a dictionary mapping agent names to maximum allowed cost in USD.
4. WHEN any agent's estimated cost exceeds its cap, THE function SHALL raise `AssertionError` listing each agent that exceeded its cap, the cap value, and the actual cost.

### Requirement 14: Correctness Property Eval Tests

**User Story:** As an engineer, I want property-based tests that verify invariants of agent outputs across many generated inputs, so that I can catch edge cases that example-based tests miss.

#### Acceptance Criteria

1. THE Eval_Suite SHALL include a Hypothesis property test that generates arbitrary valid input briefs (with randomized feature_summary, goals, timing, and user_summary strings) and verifies that the Run_Manifest captures a non-empty input_brief_hash for each generated input.
2. THE Eval_Suite SHALL include a Hypothesis property test that generates arbitrary Run_Records with varying numbers of LLM_Call_Records and verifies that the Cost_Meter total equals the sum of individual call costs (additive invariant).
3. THE Eval_Suite SHALL include a Hypothesis property test that generates arbitrary Trace trees and verifies that every child Span's time range falls within its parent Span's time range (containment invariant).
4. THE Eval_Suite SHALL include a Hypothesis property test that generates arbitrary Run_Records and verifies that serializing to JSON and deserializing back produces an equal Run_Record (round-trip property).

### Requirement 15: Run Record Serialization Round-Trip

**User Story:** As an engineer, I want Run_Records to serialize to JSON and deserialize back without data loss, so that I can store recordings on disk and load them for replay and evaluation.

#### Acceptance Criteria

1. THE Run_Record Pydantic model SHALL serialize to JSON via `model_dump_json()` and deserialize via `model_validate_json()` producing an equal object.
2. THE Run_Record JSON format SHALL use ISO 8601 strings for any datetime fields and float seconds for duration fields.
3. THE Run_Record JSON file SHALL be written with 2-space indentation for human readability.
4. FOR ALL valid Run_Record instances, serializing to JSON then deserializing SHALL produce an object where every field compares equal to the original (round-trip property). This property SHALL be tested with Hypothesis.
