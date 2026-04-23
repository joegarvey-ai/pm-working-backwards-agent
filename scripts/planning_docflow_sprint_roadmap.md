---
date: 2026-04-23
project: DocFlow AI (DocSync)
type: sprint planning
inputs:
  - BRD from pipeline run (output/brd_*_v1.0.md, 104 KB, 4/23/2026)
  - Existing docflow-ai repo (src/docflow_ai/)
  - Stakeholder feedback (April 2026, fast-track detection)
  - Gap analysis (scripts/gap_analysis_docflow_vs_buildspec.md)
---

# DocFlow AI Sprint Roadmap: BRD to Code

## How to Use This Document

Each section maps a BRD requirement to what exists in the repo, what's missing, and where to find the details. For each gap:
- **BRD reference**: the FR/NFR number and section in `output/brd_*_v1.0.md`
- **Repo reference**: the file(s) in `src/docflow_ai/` that relate
- **What exists**: what's already built
- **What's missing**: what needs to be added
- **Where to find details**: which BRD section has acceptance criteria, code samples, data models

---

## Sprint 1: Fast-Track Detection Mode (FR-004) — HIGHEST PRIORITY

Stakeholder's core ask. Nothing in the repo addresses it.

### BRD Reference
- FR-004 in `output/brd_*_v1.0.md`, section 5
- User story US-004 (on-call writer for fast-track tickets)
- Architecture diagram: "Fast-track npm/agent (1h SLA)" EventBridge path

### Repo Reference
- `src/docflow_ai/infrastructure/eventbridge.py`
- `src/docflow_ai/handlers/event_router.py`
- `src/docflow_ai/services/drift_detector.py`

### What Exists
- EventBridge config with CodeChange event rules
- Event router classifying files by pattern
- Drift detector with severity classification
- Daily scheduled drift scan

### What's Missing
1. npm publish event listener (new EventBridge rule)
2. Agent commit recognition (commit metadata/author pattern matching)
3. Priority queue for generation jobs (P0 fast-track, P1 schema, P2 general)
4. 1-hour SLA enforcement (CloudWatch alarm)
5. Fast-track JIRA ticket labeling

### Where to Find Details
- BRD FR-004: full acceptance criteria, EventBridge rule pattern, JIRA ticket schema

---

## Sprint 2: Peer Review Workflow (FR-002) — P0

BRD requires two-writer review gate. Repo has simple approval check only.

### BRD Reference
- FR-002 in `output/brd_*_v1.0.md`, section 5
- User stories US-001, US-002

### Repo Reference
- `src/docflow_ai/utils/auth_handler.py`
- `src/docflow_ai/handlers/dashboard_api.py`

### What Exists
- `check_publication_gate()`: checks status + approver_id
- `check_approval_authorization()`: checks Technical_Writer role
- Dashboard API handlers (pure functions, not wired to Lambda)

### What's Missing
1. Peer Review Queue DynamoDB table
2. Self-approval prevention (same identity check)
3. Status state machine: draft -> pending_review -> changes_requested -> approved -> published
4. Inline comments on review
5. Slack notifications for review routing

### Where to Find Details
- BRD FR-002: DynamoDB schema, Slack payload, acceptance criteria

---

## Sprint 3: Writer Review UI (FR-002) — P0

API handlers exist, no web interface.

### BRD Reference
- FR-002 in `output/brd_*_v1.0.md`, section 5

### Repo Reference
- `src/docflow_ai/handlers/dashboard_api.py` (11 endpoints)
- `.kiro/specs/docflow-ai/design.md`

### What Exists
- Pure-function API handlers for all 11 dashboard endpoints
- API Gateway configuration

### What's Missing
1. Web application (SPA) on CloudFront + S3
2. Side-by-side draft view (generated left, live right)
3. Gap annotation panel with status indicators
4. Inline editing with 5-second auto-save
5. Quality check workflow (Acrolinx/Vale results)
6. Keyboard navigation per WCAG 2.1 AA

### Where to Find Details
- BRD FR-002 acceptance criteria
- Design brief: `output/design_brief_*_v1.0.md` (screen inventory, user flows)
- `.kiro/specs/docflow-ai/design.md`

---

## Sprint 4: JIRA Integration (FR-003, FR-004) — P0

Drift detection auto-creates JIRA tickets.

### BRD Reference
- FR-003 and FR-004 in `output/brd_*_v1.0.md`, section 5

### Repo Reference
- `src/docflow_ai/services/drift_detector.py`
- `src/docflow_ai/models/drift_alert.py`

### What Exists
- Drift alerts with severity classification
- DriftAlert model with source_change details
- Notification service (SNS with logging fallback)

### What's Missing
1. JIRA API client (REST API ticket creation)
2. JIRA ticket schema (page_id, drift_type, severity, changed_fields, correction, assigned_writer, SLA label)
3. Fast-track labeling for npm/agent tickets
4. Ticket-to-alert linking

### Where to Find Details
- BRD FR-003: JIRA ticket schema code sample
- BRD FR-004: fast-track JIRA ticket schema

---

## Sprint 5: Confidence Scoring API (FR-005) — P1

Downstream consumers query page confidence.

### BRD Reference
- FR-005 in `output/brd_*_v1.0.md`, section 5
- User story US-006 (DevAssistant RAG indexing)

### Repo Reference
- `src/docflow_ai/models/front_matter.py` (confidence_score field)
- `src/docflow_ai/services/health_metrics.py`

### What Exists
- `FrontMatter.confidence_score` (0.0 to 1.0)
- `HealthMetrics` aggregation functions
- Dashboard API health endpoint

### What's Missing
1. Public API endpoint for confidence queries
2. Filtering by confidence threshold (min_confidence parameter)
3. DevAssistant RAG integration (exclude low-confidence pages)
4. Score update on each governance pass

### Where to Find Details
- BRD FR-005: API schema, DynamoDB update pattern, acceptance criteria

---

## Sprint 6: Step Functions Orchestration — P1

Lambda handlers exist, no workflow orchestration.

### BRD Reference
- BRD section 3 (architecture) and section 7 (technical context)

### Repo Reference
- `src/docflow_ai/pipelines/generation_pipeline.py`
- `src/docflow_ai/pipelines/drift_pipeline.py`

### What Exists
- GenerationPipeline: end-to-end webhook-to-draft in Python
- DriftPipeline: end-to-end drift detection in Python
- Lambda function configurations

### What's Missing
1. Step Functions state machine for generation workflow
2. Step Functions state machine for drift detection
3. Error handling states (retry, catch, fallback)
4. CloudFormation/CDK templates

### Where to Find Details
- BRD section 3 architecture diagram
- `.kiro/specs/docflow-ai/design.md` (sequence diagrams)

---

## Sprint 7: Acrolinx/Vale Integration — P1

Style checking is stubbed.

### BRD Reference
- FR-001 (80% first-pass compliance target)
- FR-002 (quality check before submission)

### Repo Reference
- `src/docflow_ai/services/style_checker.py`

### What Exists
- StyleChecker with pluggable backend pattern
- Built-in POC rules (sentence length, weak openers)
- Acrolinx and Vale backends are no-op stubs

### What's Missing
1. Acrolinx API client
2. Vale CLI integration
3. Gate results in notification payload
4. 80% target tracking metric

### Where to Find Details
- BRD FR-001 and FR-002 acceptance criteria
- Existing `style_checker.py` has the pluggable pattern ready

---

## Priority Order

1. Sprint 1 (Fast-track mode) — stakeholder deadline V0.24 July 2026
2. Sprint 2 (Peer review) — hard architectural requirement, blocks Sprint 3
3. Sprint 4 (JIRA integration) — needed by both fast-track and standard drift
4. Sprint 3 (Writer review UI) — depends on Sprint 2
5. Sprint 5 (Confidence scoring API) — P1, DevAssistant integration
6. Sprint 6 (Step Functions) — P1, production deployment
7. Sprint 7 (Acrolinx/Vale) — P1, quality gate enforcement

## Reference Files

| Document | Location |
|----------|----------|
| BRD (with stakeholder feedback) | `output/brd_A_multi-agent_technical_documentation_system_with_v1.0.md` |
| Research brief (Dovetail data) | `output/research_brief_20260422_132421.md` |
| PRFAQ | `output/prfaq_A_multi-agent_technical_documentation_system_with_v1.0.md` |
| Design brief | `output/design_brief_A_multi-agent_technical_documentation_system_with_v1.0.md` |
| Build spec reference | `output/build_spec_A_multi-agent_technical_documentation_system_with_kiro.md` |
| Kiro-formatted spec | `output/build_spec_A_multi-agent_technical_documentation_system_with_kiro_formatted.md` |
| Gap analysis | `scripts/gap_analysis_docflow_vs_buildspec.md` |
| Existing repo | `src/docflow_ai/` and `https://github.com/joegarvey-ai/docflow-ai` |
| Kiro specs | `.kiro/specs/docflow-ai/` (requirements.md, design.md, tasks.md) |
| Input brief | `input/tech_docs_integrator.yaml` |
| Stakeholder feedback | In `input/tech_docs_integrator.yaml` business_context field |
