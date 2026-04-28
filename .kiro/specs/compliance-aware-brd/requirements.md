# Requirements Document

## Introduction

This feature adds a compliance-aware workstream to the existing BRD pipeline so that product planning artifacts capture data handling, privacy, vendor risk, and launch readiness rigor alongside the existing structure and cost-risk content. The workstream is introduced as a new async sibling task, `brd_compliance_task`, running in parallel with `brd_structure_task` and `brd_cost_risk_task`. Its typed output is merged into the final BRD by the existing assembly task, and the build spec agent renders the new content without structural change. The PRFAQ agent also gains a data handling section so the compliance task has an upstream anchor.

The feature is scoped to priorities 1 through 3 from the prior analysis: a data handling section in PRFAQ and BRD, privacy and compliance-gate sections in BRD, and a launch readiness checklist section inside BRD. The language is generic and public-repo-safe. No organization-internal portal names, policy numbers, or tool brands appear in prompts, schemas, or outputs.

## Glossary

- **PRFAQ_Agent**: The existing CrewAI agent defined in `src/pm_agent_system/config/agents.yaml` that produces a Working Backwards document validated against `PRFAQOutput`.
- **BRD_Structure_Agent**: The existing async BRD agent that produces `BRDStructureOutput`.
- **BRD_Cost_Risk_Agent**: The existing async BRD agent that produces `BRDCostRiskOutput`.
- **BRD_Compliance_Agent**: The new async BRD agent introduced by this feature. Produces `BRDComplianceOutput`.
- **BRD_Assembly_Task**: The existing task that merges BRD intermediates into the final `BRDOutput`.
- **Build_Spec_Agent**: The existing agent that renders the final BRD into a tool-specific build spec.
- **Data_Classification**: One of the five levels used to tag each data element: Public, Confidential, Highly Confidential, Restricted, Critical.
- **Dataset_Classification**: The highest `Data_Classification` value among all elements in a dataset.
- **Vendor_Risk_Scenario**: One of the seven generic third-party scenarios (data sharing, data handling, content hosting, product development, environment connection, SaaS usage, endorsement or referral).
- **Compliance_Gate**: A named review checkpoint (security review, privacy review, legal or contract review, procurement review) that applies before launch.
- **Launch_Readiness_Checklist**: A tabular list of gate items with columns Item, Applies To, Gate Owner, Evidence Reference.
- **STRIDE_Stub**: A structured-text threat model scaffold covering Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege.
- **RACI_Matrix**: A responsibility assignment table with Responsible, Accountable, Consulted, Informed columns across generic owners (PM, Tech Lead, Engineer, Legal, Security, Privacy).
- **Banned_Word_List**: The project-standard list of prohibited words enforced across agent prompts and outputs.
- **Full_Pipeline_Crew**: The CrewAI crew defined in `src/pm_agent_system/crew.py` that runs research through BRD end to end.
- **Split_BRD_Crew**: The CrewAI crew that runs only the BRD sub-pipeline from a prior PRFAQ.
- **Baseline_Wall_Clock**: The measured end-to-end runtime of `Full_Pipeline_Crew` and `Split_BRD_Crew` prior to this feature landing.

## Scope Summary

- **MUST-have (Priorities 1 through 3)**: Requirements 1 through 10.
- **SHOULD-have (optional)**: Requirement 11 (no-tools `brd_assembly_agent`).
- **NICE-to-have (future, captured not implemented)**: Requirement 12 (deferred items).

## Requirements

### Requirement 1: PRFAQ Data Handling Section

**User Story:** As a PM, I want the PRFAQ to include a data handling section, so that the downstream BRD compliance task has an upstream anchor and the PRFAQ surfaces data decisions early.

#### Acceptance Criteria

1. THE PRFAQ_Agent SHALL produce a data handling section that enumerates each data element the product will collect, process, store, or transmit.
2. THE PRFAQ_Agent SHALL tag each enumerated data element with one Data_Classification value from the set {Public, Confidential, Highly Confidential, Restricted, Critical}.
3. IF the PM input contains no information about data handling, THEN THE PRFAQ_Agent SHALL record a gap entry in `appendix_gaps` and SHALL NOT fabricate data elements.
4. THE PRFAQOutput Pydantic model SHALL expose a typed field that stores the data handling section content in a structured form suitable for downstream consumption.
5. THE PRFAQ_Agent SHALL produce output that contains zero words from the Banned_Word_List and zero em dashes used as punctuation.

### Requirement 2: New BRD Compliance Agent and Task

**User Story:** As a PM, I want a dedicated compliance agent producing a typed intermediate, so that compliance content is generated in parallel with structure and cost-risk content and stays isolated from their tool sets.

#### Acceptance Criteria

1. THE `src/pm_agent_system/config/agents.yaml` file SHALL define a `brd_compliance_agent` entry with a role, goal, and backstory scoped to compliance content.
2. THE `brd_compliance_agent` SHALL be configured with FileReaderTool as a required tool and TavilySearchTool as an optional tool, and SHALL NOT be configured with other tools.
3. THE `src/pm_agent_system/config/tasks.yaml` file SHALL define a `brd_compliance_task` entry whose expected output is `BRDComplianceOutput`.
4. THE `brd_compliance_task` SHALL be attached to `brd_compliance_agent` and SHALL NOT share agents with `brd_structure_task` or `brd_cost_risk_task`.
5. WHEN the `brd_compliance_task` is scheduled in `Full_Pipeline_Crew` or `Split_BRD_Crew`, THE crew orchestrator in `src/pm_agent_system/crew.py` SHALL run it as an async sibling of `brd_structure_task` and `brd_cost_risk_task`.

### Requirement 3: BRDComplianceOutput Pydantic Model

**User Story:** As an engineer, I want a typed intermediate model, so that compliance content flows through the pipeline with schema validation and clear field boundaries.

#### Acceptance Criteria

1. THE `src/pm_agent_system/models/brd_intermediate.py` module SHALL define a `BRDComplianceOutput` Pydantic model alongside `BRDStructureOutput` and `BRDCostRiskOutput`.
2. THE BRDComplianceOutput model SHALL define a field that stores the list of data elements with classifications, a field that stores the Dataset_Classification, a field that stores vendor considerations, a field that stores privacy risks with mitigations, a field that stores Compliance_Gate entries, a field that stores the Launch_Readiness_Checklist rows, and a field that stores post-launch maintenance notes.
3. THE BRDComplianceOutput model SHALL constrain each element's classification to one of {Public, Confidential, Highly Confidential, Restricted, Critical} through an enum or validator.
4. THE BRDComplianceOutput model SHALL constrain each gate owner in the Launch_Readiness_Checklist to one of {PM, Tech Lead, Engineer, Legal, Security, Privacy}.
5. THE BRDComplianceOutput model SHALL define a field that records a gap flag when upstream input is insufficient to produce data handling content.

### Requirement 4: BRDOutput Compliance Fields and Assembly

**User Story:** As a PM, I want the assembled BRD to include the compliance content, so that the final artifact stakeholders review is complete.

#### Acceptance Criteria

1. THE `src/pm_agent_system/models/brd_output.py` module SHALL extend `BRDOutput` with fields that hold the data handling section, vendor considerations section, privacy considerations section, Compliance_Gate list, Launch_Readiness_Checklist, and post-launch maintenance section.
2. THE existing `brd_assembly_task` SHALL consume three typed intermediates (`BRDStructureOutput`, `BRDCostRiskOutput`, `BRDComplianceOutput`) and SHALL populate the extended `BRDOutput` fields from the compliance intermediate.
3. WHEN any one of the three intermediates is missing or invalid, THE `brd_assembly_task` SHALL surface an assembly error that names the missing intermediate and SHALL NOT emit a partial BRDOutput.
4. THE `brd_assembly_task` output SHALL carry the Dataset_Classification value through to `BRDOutput` without modification.

### Requirement 5: Data Handling Content Rules

**User Story:** As a PM, I want the compliance task to produce a disciplined data handling section, so that every data element is classified and the dataset classification is derived consistently.

#### Acceptance Criteria

1. THE BRD_Compliance_Agent SHALL enumerate each data element the product will collect, process, store, or transmit, grounded in the PRFAQ data handling section.
2. THE BRD_Compliance_Agent SHALL assign each data element one Data_Classification value from the constrained set.
3. THE BRD_Compliance_Agent SHALL derive the Dataset_Classification as the highest Data_Classification value among enumerated elements, using the ordering Public < Confidential < Highly Confidential < Restricted < Critical.
4. IF the PRFAQ data handling section is empty or marks data handling as a gap, THEN THE BRD_Compliance_Agent SHALL set the gap flag on BRDComplianceOutput, SHALL record a gap entry describing the missing input, and SHALL NOT fabricate data elements.
5. THE BRD_Compliance_Agent SHALL produce the data handling section using "The system shall..." phrasing for any requirement-style statements.

### Requirement 6: Vendor Considerations

**User Story:** As a PM, I want the compliance task to detect third-party involvement and surface vendor risk in generic language, so that procurement and contract considerations are captured without organization-internal nouns.

#### Acceptance Criteria

1. THE BRD_Compliance_Agent SHALL evaluate PRFAQ and PM input against the seven Vendor_Risk_Scenario categories and SHALL record which scenarios apply.
2. WHEN at least one Vendor_Risk_Scenario applies, THE BRD_Compliance_Agent SHALL produce vendor considerations that name contract review, security review expectations, and data sharing boundaries in generic language.
3. WHEN no Vendor_Risk_Scenario applies, THE BRD_Compliance_Agent SHALL state explicitly that no third party is involved in the vendor considerations field.
4. THE BRD_Compliance_Agent SHALL NOT include any organization-internal portal name, service brand, policy number, or domain reference in the vendor considerations field.

### Requirement 7: Privacy Considerations

**User Story:** As a PM, I want privacy risks and mitigations tied to the data classification, so that privacy design review is triggered when personal data is handled.

#### Acceptance Criteria

1. THE BRD_Compliance_Agent SHALL produce privacy risks grounded in the data handling classifications recorded in the same BRDComplianceOutput.
2. THE BRD_Compliance_Agent SHALL propose mitigations covering encryption in transit, encryption at rest, access controls, data minimization, and retention limits, scoped to the relevant data elements.
3. WHEN any enumerated data element carries a classification of Confidential or higher and represents personal data, THE BRD_Compliance_Agent SHALL set a privacy design review flag to true in BRDComplianceOutput.
4. WHERE the Full_Pipeline_Crew is running without a Tavily API key, THE BRD_Compliance_Agent SHALL produce privacy considerations using only PRFAQ and PM input and SHALL record any regulation lookups as gaps rather than failing the task.

### Requirement 8: Compliance Gates as Parallel Workstreams

**User Story:** As a PM, I want compliance reviews surfaced as parallel workstreams with the start-early rule stated, so that teams do not sequence reviews late in the plan.

#### Acceptance Criteria

1. THE BRD_Compliance_Agent SHALL list the applicable Compliance_Gate entries from the set {security review, privacy review, legal or contract review, procurement review}, including only those that apply.
2. THE BRD_Compliance_Agent SHALL include the guidance string "start early, run in parallel, do not launch with open Critical or High findings" as an explicit Compliance_Gate note field.
3. THE BRD_Compliance_Agent SHALL NOT describe Compliance_Gate entries as a sequential chain.
4. THE BRD_Compliance_Agent SHALL NOT reference organization-internal ticket systems, portal names, or policy numbers in any Compliance_Gate entry.

### Requirement 9: Launch Readiness Checklist

**User Story:** As a PM, I want a launch readiness checklist inside the BRD, so that pre-launch gate items and owners are explicit without needing a separate agent.

#### Acceptance Criteria

1. THE BRD_Compliance_Agent SHALL produce a Launch_Readiness_Checklist with columns Item, Applies To, Gate Owner, Evidence Reference.
2. THE Launch_Readiness_Checklist SHALL include at minimum the following items: data classification sign-off, privacy mitigation sign-off, security review status, monitoring or alarm setup, runbook availability, rollback plan.
3. THE BRD_Compliance_Agent SHALL restrict Gate Owner values to the set {PM, Tech Lead, Engineer, Legal, Security, Privacy}.
4. THE BRD_Compliance_Agent SHALL populate the Evidence Reference column with a pointer to the producing section (for example, a BRD section name or a PRFAQ reference), and SHALL leave the value empty when no evidence is yet available rather than fabricating a link.

### Requirement 10: Post-Launch Maintenance Section

**User Story:** As a PM, I want a post-launch maintenance section, so that recertification cadence and ownership pointers are captured before launch.

#### Acceptance Criteria

1. THE BRD_Compliance_Agent SHALL produce a post-launch maintenance section that names a recertification cadence for vendor access and data classifications in generic framing.
2. THE BRD_Compliance_Agent SHALL list triggers that require a data classification update, including the addition of new data elements, a change in data sources, and a change in vendor scope.
3. THE BRD_Compliance_Agent SHALL include runbook and ownership pointers referencing the Launch_Readiness_Checklist rows rather than duplicating content.

### Requirement 11: Build Spec Rendering of Compliance Content

**User Story:** As an engineer, I want the build spec to render the compliance content (including STRIDE stub and RACI matrix) without a new agent, so that downstream tools receive the full context.

#### Acceptance Criteria

1. THE Build_Spec_Agent SHALL consume the compliance fields on `BRDOutput` through its existing input chain and SHALL NOT require a new task or agent to do so.
2. THE `src/pm_agent_system/utils/render_build_spec.py` module SHALL render the data handling, vendor considerations, privacy considerations, Compliance_Gate, Launch_Readiness_Checklist, and post-launch maintenance sections into the existing build spec output.
3. THE Build_Spec_Agent SHALL render a STRIDE_Stub as structured text with one subsection per category (Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege) and SHALL NOT emit an SVG or other image artifact.
4. WHERE a Vendor_Risk_Scenario applies or the privacy design review flag is true, THE Build_Spec_Agent SHALL render a RACI_Matrix with columns Responsible, Accountable, Consulted, Informed scoped to the set {PM, Tech Lead, Engineer, Legal, Security, Privacy}.
5. THE Build_Spec_Agent SHALL NOT introduce any new CrewAI agent or task as part of this feature.

### Requirement 12: BRD Markdown Rendering

**User Story:** As a PM, I want the assembled BRD markdown to show the new compliance sections, so that reviewers see them in the canonical output file.

#### Acceptance Criteria

1. THE `src/pm_agent_system/utils/render_brd.py` module SHALL render the data handling section, vendor considerations section, privacy considerations section, Compliance_Gate list, Launch_Readiness_Checklist as a markdown table, and post-launch maintenance section in a deterministic order after existing sections.
2. WHEN the BRDComplianceOutput gap flag is true, THE `render_brd.py` module SHALL render a visible gap notice in the data handling section that names the missing input.
3. THE `render_brd.py` output SHALL contain zero words from the Banned_Word_List and zero em dashes used as punctuation.

### Requirement 13: Style and Voice Constraints

**User Story:** As a PM, I want the compliance content to match the project voice, so that the BRD reads consistently across sections.

#### Acceptance Criteria

1. THE BRD_Compliance_Agent prompt in `tasks.yaml` SHALL enumerate the Banned_Word_List and SHALL instruct the agent to produce output containing zero occurrences of those words.
2. THE BRD_Compliance_Agent prompt SHALL prohibit em dashes used as punctuation, contrast hooks, and rhetorical questions used as section openers.
3. THE BRD_Compliance_Agent prompt SHALL instruct the agent to default technical references to AWS services (Lambda, DynamoDB, Cognito, API Gateway, S3, CloudFront, KMS, CloudWatch) and SHALL prohibit references to Supabase, Firebase, Vercel, and other non-enterprise services in default output.
4. THE BRD_Compliance_Agent prompt SHALL require requirement-style statements to use "The system shall..." phrasing.
5. THE BRD_Compliance_Agent prompt and output SHALL NOT contain organization-internal portal names, service brands, policy numbers, or internal URL patterns.

### Requirement 14: Parallel Execution and Latency

**User Story:** As a PM, I want the new task to run async in parallel, so that end-to-end runtime stays within the current envelope.

#### Acceptance Criteria

1. THE `brd_compliance_task` SHALL be configured as async in `Full_Pipeline_Crew` and `Split_BRD_Crew`.
2. WHEN `Full_Pipeline_Crew` runs end to end on a reference input, THE measured wall clock time SHALL NOT exceed the Baseline_Wall_Clock by more than 10 percent.
3. WHEN `Split_BRD_Crew` runs end to end on a reference input, THE measured wall clock time SHALL NOT exceed the Baseline_Wall_Clock for that crew by more than 10 percent.
4. THE `brd_compliance_task` SHALL NOT block `brd_structure_task` or `brd_cost_risk_task` from starting or completing.

### Requirement 15: Error and Missing-Input Handling

**User Story:** As an operator, I want the pipeline to handle missing inputs and unset tokens without crashing, so that runs degrade gracefully.

#### Acceptance Criteria

1. IF the `DOVETAIL_API_TOKEN` environment variable is unset, THEN THE BRD_Compliance_Agent SHALL continue to run without invoking any Dovetail code path.
2. IF the PRFAQ data handling section is absent from the upstream input, THEN THE BRD_Compliance_Agent SHALL set the gap flag, record a descriptive gap entry, and return a valid BRDComplianceOutput.
3. IF the PM input file referenced by FileReaderTool is missing, THEN THE BRD_Compliance_Agent SHALL return a BRDComplianceOutput with the gap flag set and SHALL NOT raise an unhandled exception.
4. IF the Tavily API key is unset and the BRD_Compliance_Agent attempts a privacy regulation lookup, THEN THE BRD_Compliance_Agent SHALL record the attempted lookup as a gap and SHALL continue the task.

### Requirement 16: Unit and Integration Tests

**User Story:** As an engineer, I want tests that cover the new model, prompt rendering, and integrated crew output, so that regressions are caught early.

#### Acceptance Criteria

1. THE test suite under `tests/` SHALL include a unit test module that validates `BRDComplianceOutput` accepts valid inputs, rejects invalid Data_Classification values, and rejects Gate Owner values outside the constrained set.
2. THE test suite SHALL include a unit test that renders the `brd_compliance_task` prompt and asserts the prompt contains zero words from the Banned_Word_List and enumerates the five Data_Classification levels.
3. THE test suite SHALL include an integration test that runs `Split_BRD_Crew` against a minimal input fixture and asserts the resulting `BRDOutput` contains populated data handling, Compliance_Gate, and Launch_Readiness_Checklist fields.
4. THE test suite SHALL include a test that runs the BRD pipeline with a PRFAQ fixture lacking a data handling section and asserts that the BRDComplianceOutput gap flag is true and no data elements are fabricated.
5. THE test suite SHALL include a test that runs with `DOVETAIL_API_TOKEN` unset and asserts that the BRD pipeline completes without raising.

### Requirement 17 (SHOULD): Optional No-Tools Assembly Agent

**User Story:** As a PM, I want the option to extract a no-tools `brd_assembly_agent` mirroring the research synthesis pattern, so that assembly latency is protected as inputs grow.

#### Acceptance Criteria

1. WHERE this requirement is approved for implementation, THE `src/pm_agent_system/config/agents.yaml` file SHALL define a `brd_assembly_agent` entry with no tools attached.
2. WHERE this requirement is approved for implementation, THE `brd_assembly_task` SHALL be attached to the new `brd_assembly_agent` and SHALL retain identical input and output contracts.
3. WHERE this requirement is deferred, THE feature SHALL be implementable without the `brd_assembly_agent` change and all other requirements SHALL remain satisfiable.

### Requirement 18 (NICE): Deferred Future Work

**User Story:** As a PM, I want future-work items captured in the spec, so that scope stays controlled now and the backlog is visible.

#### Acceptance Criteria

1. THE requirements document SHALL record the following items as out of scope for this feature: an organization-internal mode with internal nouns, a separate launch readiness agent or CLI subcommand, changes to research, design brief, or build spec agent structure, new MCP tools or external integrations, and auto-generated STRIDE diagrams as SVG.
2. THE requirements document SHALL NOT expand scope to include the deferred items unless the PM explicitly reopens scope in a later spec.
