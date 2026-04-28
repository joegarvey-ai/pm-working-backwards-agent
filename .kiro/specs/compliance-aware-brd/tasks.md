# Implementation Plan: Compliance-Aware BRD

## Overview

This plan adds the compliance-aware workstream as a strictly additive extension to the existing split BRD pipeline. New work lands in a defined order so each step is self-verifying before the next builds on it: Pydantic models first, then deterministic renderers, then agent and task prompts, then crew wiring, then BRD and build spec rendering hookup, then PRFAQ upstream changes, and finally a latency verification script.

Testing follows the project's existing convention of `uv run pytest tests/` with fixtures under `tests/fixtures/`. Property-based tests are scoped to the six correctness properties named in the design document. The optional `brd_assembly_agent` extraction (Requirement 17) is captured as an optional task group that stays deferred unless the user opts in during execution.

The implementation language is Python 3.11+, matching the existing codebase. The design uses concrete Python examples, so no language-selection question is needed.

## Tasks

- [x] 0. Add property-based testing dependency
  - [x] 0.1 Add `hypothesis>=6.0` to the dev dependency group
    - Edit `pyproject.toml` to add `hypothesis>=6.0` under the dev dependency group (follow existing formatting conventions for the group)
    - Run `uv sync --group dev` to install
    - Verify with `uv run python -c "import hypothesis; print(hypothesis.__version__)"`
    - _Validates: Requirements 16.1, 16.2 (enables property-based testing used throughout)_

- [x] 1. Add enums and shared Pydantic primitives for compliance content
  - [x] 1.1 Add `DataClassification` and `GateOwner` enums
    - Add `DataClassification` (Public, Confidential, Highly Confidential, Restricted, Critical) and `GateOwner` (PM, Tech Lead, Engineer, Legal, Security, Privacy) string enums to `src/pm_agent_system/models/brd_intermediate.py`
    - Include the private `_DATA_CLASS_ORDER` mapping used by dataset-classification derivation
    - Export both enums from `src/pm_agent_system/models/__init__.py`
    - _Validates: Requirements 3.3, 3.4, 5.2, 5.3, 9.3_
  - [x]* 1.2 Unit tests for enum value bounds
    - Add `tests/test_compliance_enums.py` asserting enum values match the constrained sets in the design
    - _Validates: Requirements 3.3, 3.4, 9.3_

- [x] 2. Add `BRDComplianceOutput` and its nested models
  - [x] 2.1 Implement nested compliance models
    - In `src/pm_agent_system/models/brd_intermediate.py`, add `DataElement`, `ComplianceGate`, `LaunchReadinessItem`, and `PrivacyConsiderations`
    - Default the `ComplianceGate.note` field to the verbatim start-early string from the design
    - _Validates: Requirements 3.2, 8.2, 9.1, 9.3, 9.4_
  - [x] 2.2 Implement `BRDComplianceOutput` with gap-flag validator
    - Add `BRDComplianceOutput` with all fields listed in the design (data_elements, dataset_classification, vendor_considerations, vendor_scenarios_applied, privacy_considerations, compliance_gates, launch_readiness_checklist, post_launch_maintenance, data_handling_gap_flag, data_handling_gaps)
    - Add the `_validate_gap_pairing` model validator that enforces the gap-flag invariant
    - Export `BRDComplianceOutput` from `src/pm_agent_system/models/__init__.py`
    - _Validates: Requirements 3.1, 3.2, 3.5, 5.4_
  - [x]* 2.3 Unit tests for `BRDComplianceOutput` validation
    - Add `tests/test_brd_compliance_output.py` covering: valid construction, invalid classification rejected, invalid gate owner rejected, gap-flag invariant rejections (gap flag True with non-empty elements, gap flag True with dataset_classification set, gap flag True with empty gaps)
    - _Validates: Requirements 3.3, 3.4, 3.5_
  - [x]* 2.4 Property test for Property 1: enum bounds at schema level
    - Add `tests/test_compliance_properties.py::test_property_1_enum_bounds`
    - **Property 1: Enum values are bounded at schema level**
    - **Validates: Requirements 1.2, 3.3, 3.4, 5.2, 9.3**
  - [x]* 2.5 Property test for Property 3: gap-flag pairing invariant
    - Add `tests/test_compliance_properties.py::test_property_3_gap_flag_pairing`
    - **Property 3: Gap flag pairing invariant**
    - **Validates: Requirements 3.5, 5.4, 15.2, 15.3**

- [x] 3. Extend `BRDOutput` with compliance fields (strictly additive)
  - [x] 3.1 Add `DataHandlingSection` and extend `BRDOutput`
    - In `src/pm_agent_system/models/brd_output.py`, add `DataHandlingSection` nested model
    - Append the six new fields from the design (data_handling_section, vendor_considerations, vendor_scenarios_applied, privacy_considerations, compliance_gates, launch_readiness_checklist, post_launch_maintenance) with defaults on every field
    - Import the shared nested models (`DataElement`, `ComplianceGate`, `LaunchReadinessItem`, `PrivacyConsiderations`) from `brd_intermediate.py` to avoid duplication
    - _Validates: Requirements 4.1_
  - [x] 3.2 Verify backward compatibility with existing fixtures
    - Add `tests/fixtures/brd_legacy.json` containing a pre-feature `BRDOutput` payload (no compliance fields)
    - Add `tests/test_brd_output_backward_compat.py` asserting `BRDOutput.model_validate(legacy_payload)` succeeds and the new fields are populated with their defaults
    - _Validates: Requirements 4.1_
  - [x]* 3.3 Unit test for assembly field preservation
    - In the same test module, assert that assembling a `BRDOutput` from three valid intermediates preserves every field byte-identically
    - _Validates: Requirements 4.2, 4.4_
  - [x]* 3.4 Property test for Property 4: assembly preserves intermediate content
    - Add `tests/test_compliance_properties.py::test_property_4_assembly_preserves_content`
    - **Property 4: Assembly preserves intermediate content**
    - **Validates: Requirements 4.2, 4.4**

- [x] 4. Extend `PRFAQOutput` with a structured `data_handling` field
  - [x] 4.1 Add `PRFAQDataElement`, `PRFAQDataHandling`, and extend `PRFAQOutput`
    - In `src/pm_agent_system/models/prfaq_output.py`, add the two nested models and append `data_handling: PRFAQDataHandling` with a default factory
    - Reuse `DataClassification` from `brd_intermediate.py` (do not redefine the enum)
    - _Validates: Requirements 1.1, 1.2, 1.4_
  - [x]* 4.2 Backward-compat test for existing PRFAQ fixtures
    - Add `tests/fixtures/prfaq_without_data_handling.json` (mirrors the pre-feature shape) and `tests/fixtures/prfaq_with_data_handling.json` (includes populated elements)
    - Add `tests/test_prfaq_output_backward_compat.py` asserting both fixtures validate and that the no-data-handling fixture defaults to an empty `PRFAQDataHandling`
    - _Validates: Requirements 1.4_

- [x] 5. Extend `CodingPromptOutput` with `stride_stub` and `raci_matrix`
  - [x] 5.1 Add `RACIRow` and extend `CodingPromptOutput`
    - In `src/pm_agent_system/models/coding_prompt_output.py`, add `RACIRow` and append `stride_stub: str = ""` plus `raci_matrix: list[RACIRow] = Field(default_factory=list)`
    - Export `RACIRow` from `src/pm_agent_system/models/__init__.py`
    - _Validates: Requirements 11.2, 11.3, 11.4_
  - [x]* 5.2 Backward-compat test for existing build-spec fixtures
    - Extend `tests/test_smoke.py` or add `tests/test_coding_prompt_output_backward_compat.py` that constructs the existing minimal `CodingPromptOutput` payload and asserts the two new fields default to empty values
    - _Validates: Requirements 11.2_

- [x] 6. Checkpoint - models are self-contained and verified
  - Ensure all tests pass with `uv run pytest tests/`, ask the user if questions arise.

- [x] 7. Implement deterministic build-spec renderers
  - [x] 7.1 Implement `render_stride_stub`
    - In `src/pm_agent_system/utils/render_build_spec.py`, add `render_stride_stub(brd_output: BRDOutput) -> str`
    - Six fixed subsection headers (Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege)
    - Trigger logic: render when any element classification is Confidential or higher, or `privacy_considerations.design_review_flag` is True, or any vendor scenario applies; otherwise return `""`
    - AWS-first phrasing per the design example (Cognito, API Gateway, TLS, KMS, CloudWatch Logs, CloudFront)
    - Zero banned words and zero em dashes in any static string
    - _Validates: Requirements 11.3, 13.3_
  - [x] 7.2 Implement `render_raci_matrix` and `render_raci_matrix_markdown`
    - In the same module, add `render_raci_matrix(brd_output) -> list[RACIRow]` returning six rows (one per `GateOwner` value) with deterministic RACI assignment as described in the design, or `[]` when no trigger condition applies
    - Add `render_raci_matrix_markdown(rows: list[RACIRow]) -> str` returning the markdown table, or `""` on empty input
    - _Validates: Requirements 11.4_
  - [x]* 7.3 Unit tests for STRIDE and RACI renderers
    - Add `tests/test_render_build_spec_compliance.py` covering: trigger conditions, empty-return-on-no-trigger, exactly six STRIDE headers, exactly six RACI rows, one Accountable and at least one Responsible per RACI table, owner enum coverage
    - _Validates: Requirements 11.3, 11.4_
  - [x]* 7.4 Property test for Property 5: rendering preservation (STRIDE and RACI half)
    - Add `tests/test_compliance_properties.py::test_property_5_stride_raci_deterministic`
    - **Property 5: BRD rendering preserves compliance content, build spec renders STRIDE and RACI deterministically (renderer half)**
    - **Validates: Requirements 11.2, 11.3, 11.4**
  - [x]* 7.5 Property test for Property 2: dataset classification is the element-wise maximum
    - Add `tests/test_compliance_properties.py::test_property_2_dataset_classification_max`
    - Use a small helper `_derive_dataset_classification(elements)` colocated with `BRDComplianceOutput` (add it in task 2.2 if not already present) and assert it equals `max(..., key=_DATA_CLASS_ORDER.get)` for non-empty input and `None` for empty
    - **Property 2: Dataset classification is the element-wise maximum**
    - **Validates: Requirements 5.3**

- [x] 8. Extend `render_brd.py` for sections 13 through 18
  - [x] 8.1 Implement renderers for the six new sections
    - In `src/pm_agent_system/utils/render_brd.py`, append section 13 (Data Handling, with elements table and dataset classification), 14 (Vendor Considerations, with explicit no-third-party string when none applies), 15 (Privacy Considerations, with design review flag), 16 (Compliance Gates, rendering the start-early note verbatim), 17 (Launch Readiness Checklist table), 18 (Post-Launch Maintenance)
    - When `data_handling_section.gap_flag` is True, render the gap notice blockquote exactly as specified in the design and skip the elements table
    - Preserve the existing twelve sections unchanged; new sections render in fixed order after the version history section
    - Zero banned words and zero em dashes in any static string
    - _Validates: Requirements 4.1, 6.3, 8.2, 12.1, 12.2, 12.3_
  - [x]* 8.2 Unit tests for BRD markdown rendering
    - Add `tests/test_render_brd_compliance.py` covering: section order, gap notice rendering when flag is True, start-early note verbatim, table header presence, static-string banned-word and em-dash absence
    - _Validates: Requirements 12.1, 12.2, 12.3_
  - [x]* 8.3 Property test for Property 5: rendering preservation (BRD markdown half)
    - Extend `tests/test_compliance_properties.py::test_property_5_brd_rendering_preservation`
    - **Property 5: BRD rendering preserves compliance content (markdown half)**
    - **Validates: Requirements 12.1, 12.2**
  - [x]* 8.4 Property test for Property 6: banned-word and em-dash absence in renderer static strings
    - Add `tests/test_compliance_properties.py::test_property_6_renderer_static_hygiene`
    - **Property 6: Banned-word and em-dash absence in renderer static strings**
    - **Validates: Requirements 12.3**

- [x] 9. Checkpoint - deterministic renderers are verified in isolation
  - Ensure all tests pass with `uv run pytest tests/`, ask the user if questions arise.

- [x] 10. Add `brd_compliance_agent` and `brd_compliance_task` prompts
  - [x] 10.1 Add agent entry in `agents.yaml`
    - In `src/pm_agent_system/config/agents.yaml`, add the `brd_compliance_agent` entry (role, goal, backstory) per the design sketch
    - Keep language generic, AWS-first, no organization-internal nouns, no em dashes as punctuation, no banned words
    - _Validates: Requirements 2.1, 13.1, 13.2, 13.3, 13.5_
  - [x] 10.2 Add task entry in `tasks.yaml`
    - In `src/pm_agent_system/config/tasks.yaml`, add the `brd_compliance_task` entry mirroring the design skeleton
    - Enumerate all five `DataClassification` levels, the seven vendor scenarios, the four compliance gates, and the six gate owner values explicitly in the prompt
    - Include the verbatim start-early note as the `ComplianceGate.note` instruction
    - Preserve the `{prfaq_path}`, `{research_path}`, `{known_constraints}`, `{business_context}` template placeholders
    - _Validates: Requirements 2.3, 2.4, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4, 9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3, 13.1, 13.2, 13.3, 13.4, 13.5, 15.1, 15.2, 15.3, 15.4_
  - [x] 10.3 Grep the new prompt content for banned words and em dashes
    - Before committing, run the project's banned-word and em-dash check against the newly added blocks in `agents.yaml` and `tasks.yaml` (the banned word list is defined in the existing agent prompts and style steering; reuse that list)
    - Fix any hits and re-run until clean
    - _Validates: Requirements 13.1, 13.2, 13.5_
  - [x]* 10.4 Prompt-rendering test
    - Add `tests/test_compliance_prompt_rendering.py` that loads `tasks.yaml`, renders the `brd_compliance_task` description with a representative payload, and asserts: zero banned words, zero em dashes used as punctuation, all five classification levels named explicitly, all four compliance gates named explicitly, all six gate owners named explicitly
    - _Validates: Requirements 13.1, 13.2, 13.3, 13.4, 13.5_

- [x] 11. Update `brd_assembly_task` description for three-way merge
  - [x] 11.1 Update `brd_assembly_task` in `tasks.yaml`
    - Edit `src/pm_agent_system/config/tasks.yaml` so the `brd_assembly_task` description lists three inputs (structure, cost-risk, compliance), instructs verbatim copy of compliance fields into the extended `BRDOutput`, and names the assembly-error behavior when an intermediate is missing or invalid
    - Preserve all existing template placeholders
    - _Validates: Requirements 4.2, 4.3, 4.4_
  - [x] 11.2 Grep the updated prompt content for banned words and em dashes
    - Same enforcement as task 10.3 for the edited block
    - _Validates: Requirements 13.1, 13.2_

- [x] 12. Wire the compliance sibling into both crews
  - [x] 12.1 Add `brd_compliance_agent()` factory method in `crew.py`
    - In `src/pm_agent_system/crew.py`, add a `@agent` decorated `brd_compliance_agent(self) -> Agent` method that returns an `Agent` with `config=self.agents_config["brd_compliance_agent"]`, tools `[FileReaderTool(), TavilySearchTool()]` guarded on `TAVILY_API_KEY` presence (mirror how the existing code gates optional tools), and no other tools
    - _Validates: Requirements 2.1, 2.2, 15.1, 15.4_
  - [x] 12.2 Extend `full_pipeline_crew` to run compliance as a third async sibling
    - In `full_pipeline_crew`, define `brd_compliance_task = Task(...)` mirroring the `brd_cost_risk_task` pattern (same `context=[research, prfaq_task]`, `output_pydantic=BRDComplianceOutput`, `async_execution=True`, `agent=self.brd_compliance_agent()`)
    - Extend `brd_assembly_task.context` to `[brd_structure_task, brd_cost_risk_task, brd_compliance_task]`
    - Append `brd_compliance_task` to the crew's `tasks.extend(...)` list and append `self.brd_compliance_agent()` to `agents_list`
    - Do not restructure the existing tasks; this must be strictly additive
    - _Validates: Requirements 2.5, 4.2, 14.1, 14.4_
  - [x] 12.3 Extend `split_brd_crew` identically
    - Add the same `brd_compliance_task` to `split_brd_crew`, extend the assembly task's context, add the agent to the crew's `agents=[...]` list, and include the task in the crew's `tasks=[...]` list
    - _Validates: Requirements 2.5, 4.2, 14.1, 14.4_
  - [x]* 12.4 Integration test: Split BRD crew end-to-end with clear data handling
    - Add `tests/test_split_brd_crew_compliance.py` with a minimal PRFAQ fixture (includes a clear data handling section) under `tests/fixtures/`
    - Run `split_brd_crew` and assert `BRDOutput.data_handling_section.elements`, `compliance_gates`, and `launch_readiness_checklist` are all populated
    - _Validates: Requirements 2.5, 4.2, 16.3_
  - [x]* 12.5 Integration test: gap-handling end-to-end
    - In the same module, add a test that runs the crew against a PRFAQ fixture lacking a data handling section and asserts `data_handling_section.gap_flag` is True, `elements` is empty, and the gap notice is present in the rendered markdown
    - _Validates: Requirements 5.4, 15.2, 16.4_
  - [x]* 12.6 Integration test: `DOVETAIL_API_TOKEN` unset
    - Add a test that runs the pipeline with `DOVETAIL_API_TOKEN` unset (via `monkeypatch.delenv`) and asserts the pipeline completes without raising and `BRDComplianceOutput` still validates
    - _Validates: Requirements 15.1, 16.5_
  - [x]* 12.7 Integration test: Tavily API key unset
    - Add a test that runs the pipeline with `TAVILY_API_KEY` unset and asserts `BRDComplianceOutput` validates, with any attempted regulation lookups recorded as gaps
    - _Validates: Requirements 7.4, 15.4_

- [x] 13. Checkpoint - crew wiring is verified end to end
  - Ensure all tests pass with `uv run pytest tests/`, ask the user if questions arise.

- [x] 14. Hook deterministic STRIDE and RACI rendering into the build-spec assembly
  - [x] 14.1 Call the renderers after `formatted_spec` is produced
    - Locate the point in `src/pm_agent_system/main.py` (or wherever `BuildSpecStructureOutput` and `FormattedSpecOutput` are merged into `CodingPromptOutput`) where `formatted_spec` is finalized
    - After the LLM-produced `formatted_spec` is set, call `render_stride_stub(brd_output)` and `render_raci_matrix(brd_output)` then `render_raci_matrix_markdown(rows)`
    - Set `CodingPromptOutput.stride_stub` and `CodingPromptOutput.raci_matrix` from the renderer outputs
    - Append the rendered STRIDE markdown and then the rendered RACI markdown to `formatted_spec` in that fixed order (STRIDE before RACI, both after the main body)
    - Do not introduce any new CrewAI agent or task
    - _Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5_
  - [x]* 14.2 Unit test for the build-spec hookup
    - Add `tests/test_build_spec_stride_raci_hookup.py` that constructs a `BRDOutput` meeting trigger conditions, runs the merge or assembly helper, and asserts STRIDE precedes RACI in `formatted_spec` and both `stride_stub` and `raci_matrix` are populated on `CodingPromptOutput`
    - Add a second case where no trigger condition applies and assert both fields are empty and neither section appears in `formatted_spec`
    - _Validates: Requirements 11.2, 11.3, 11.4_

- [x] 15. Update PRFAQ prompt to enumerate data handling
  - [x] 15.1 Update `generate_prfaq` task description
    - Edit `src/pm_agent_system/config/tasks.yaml` so `generate_prfaq` includes the three numbered steps from the design: enumerate data elements, classify each, handle missing-input by recording a gap in `appendix_gaps` and setting `data_handling.gap_flag = True` with empty elements
    - Enumerate the five `DataClassification` levels explicitly in the prompt
    - Preserve all existing template placeholders
    - _Validates: Requirements 1.1, 1.2, 1.3, 1.5_
  - [x] 15.2 Grep the updated prompt content for banned words and em dashes
    - Same enforcement as task 10.3 for the edited block
    - _Validates: Requirements 1.5, 13.1, 13.2_
  - [x]* 15.3 Integration test: PRFAQ with populated data handling feeds compliance task
    - Add a test that runs the PRFAQ stage on an input with data-handling-relevant content, asserts `PRFAQOutput.data_handling.elements` is populated, and confirms the downstream compliance task consumes it
    - _Validates: Requirements 1.1, 1.2, 1.4_
  - [x]* 15.4 Integration test: PRFAQ with no data-handling input records a gap
    - Add a test that runs the PRFAQ stage on an input with no data-handling content, asserts `data_handling.gap_flag` is True, `elements` is empty, and `appendix_gaps` contains a descriptive entry
    - _Validates: Requirements 1.3_

- [x] 16. Checkpoint - PRFAQ anchor is wired and downstream consumes it
  - Ensure all tests pass with `uv run pytest tests/`, ask the user if questions arise.

- [x] 17. Documentation touch-ups
  - [x] 17.1 One-line mentions in the agent guides
    - Add a single sentence in each of `AGENTS.md`, `CLAUDE.md`, and `docs/using-with-kiro.md` noting that the BRD pipeline now runs a third async sibling (`brd_compliance_task`) alongside structure and cost-risk, with output merged into `BRDOutput`
    - Generic language only; no proprietary content
    - _Validates: Requirements 11.1, 12.1_

- [x] 18. Latency verification
  - [x] 18.1 Add `scripts/measure_brd_latency.py`
    - Create the script per the design: takes `examples/input.yaml` as input, runs three iterations each of `full_pipeline_crew` and `split_brd_crew`, captures per-task durations and total wall clock, and writes a JSON timing log
    - Include a docstring block explaining the manual run instructions (`uv run python scripts/measure_brd_latency.py`) and the +10 percent threshold against baseline
    - Do not wire this into the pytest gate; manual verification only (it requires real LLM calls)
    - _Validates: Requirements 14.2, 14.3_
  - [x] 18.2 Manual-run instructions
    - Add a short section at the top of the script (and reference it from the PR description at commit time) describing baseline capture, new-topology capture, and the +10 percent envelope check
    - _Validates: Requirements 14.1, 14.2, 14.3, 14.4_

- [x] 19. Final checkpoint - full suite passes and latency manual run is ready
  - Ensure all tests pass with `uv run pytest tests/`
  - Run the banned-word and em-dash greps one more time across `agents.yaml`, `tasks.yaml`, `render_brd.py`, and `render_build_spec.py` static strings
  - Ask the user to run `uv run python scripts/measure_brd_latency.py` and confirm the +10 percent envelope before merge

## Optional Task Group (Requirement 17 - SHOULD, opted in for this execution)

This group is optional by default. The user has opted in for this execution run. Sub-tasks remain marked with `*` per the workflow convention but will be executed alongside required tasks.

- [x]* 20.1 Add `brd_assembly_agent` with no tools in `agents.yaml`
  - Add the entry per the design sketch (role, goal, backstory); no tools attached
  - _Validates: Requirements 17.1_
- [x]* 20.2 Attach `brd_assembly_task` to `brd_assembly_agent`
  - In `src/pm_agent_system/config/tasks.yaml`, keep the task description unchanged
  - In `src/pm_agent_system/crew.py`, swap `agent=self.brd_agent()` to `agent=self.brd_assembly_agent()` on the `brd_assembly_task` in both `full_pipeline_crew` and `split_brd_crew`
  - Add `self.brd_assembly_agent()` to each crew's agent list
  - Input and output contracts remain identical
  - _Validates: Requirements 17.2_
- [x]* 20.3 Grep the new agent block for banned words and em dashes
  - Same enforcement pattern as tasks 10.3 and 11.2
  - _Validates: Requirements 13.1, 13.2_
- [x]* 20.4 Unit test that `brd_assembly_agent` has no tools
  - Add an assertion in `tests/test_split_brd_crew_compliance.py` that the wired assembly agent's tool list is empty when this path is enabled
  - _Validates: Requirements 17.1_

## Dependency and Infrastructure Notes

- **Property-based testing framework.** `pyproject.toml` currently lists no PBT library (no `hypothesis`, no `pytest-hypothesis`, no `crosshair`). Tasks 2.4, 2.5, 3.4, 7.4, 7.5, 8.3, and 8.4 depend on a PBT framework. Before running those property tests, add `hypothesis>=6.0` to the `dev` dependency group in `pyproject.toml` and run `uv sync --group dev`. This requires user approval per the project convention: "Do not add new top-level dependencies without updating `pyproject.toml`." The infrastructure sub-task is captured here rather than as a task to preserve the property-test ordering.
- **Banned-word list source.** The banned word list is defined in existing agent prompts and the project's style steering files. Tasks 10.3, 11.2, 15.2, 20.3, and 19 reuse that list; no new list is introduced.
- **Fixtures directory.** `tests/fixtures/` already exists. New fixtures land there alongside existing ones.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP. Optional sub-tasks cover unit tests, property tests, integration tests, and the Requirement 17 extraction group.
- Every task references specific sub-requirement IDs for traceability.
- Checkpoints (tasks 6, 9, 13, 16, 19) gate progress: each one ensures the preceding work is verified in isolation before the next builds on it.
- Property-based tests validate the six universal correctness properties named in the design document. Each property is covered by its own sub-task and references its property number.
- Unit tests validate specific examples, edge cases, and rejection paths.
- Integration tests cover end-to-end pipeline wiring, gap handling, and graceful degradation.
- Latency verification (task 18) is a manual-run step, not an automated gate, because it requires real LLM calls.

## Workflow Completion

This workflow is complete once `tasks.md` is created. The Feature Requirements-First workflow produces planning artifacts only; no implementation happens during planning. To begin implementation, open `.kiro/specs/compliance-aware-brd/tasks.md` and click "Start task" next to the first unchecked item.
