---
date: 2026-04-21
project: DocFlow AI
type: gap analysis
inputs:
  - docflow-ai repo (local src/docflow_ai/)
  - build spec from pipeline run (output/build_spec_*_kiro.md)
  - stakeholder feedback on release velocity
---

# Gap Analysis: DocFlow AI Repo vs New Build Spec vs Stakeholder Feedback

## Executive Summary

The existing docflow-ai codebase is a solid foundation with correct architecture and clean code, but it's a POC skeleton: core logic is implemented, external integrations are stubbed, there's no deployment automation, no tests, and no UI. The new build spec from the pipeline run is more detailed in its requirements (EARS notation, acceptance criteria, data model schemas) but architecturally aligned with what's already built. The stakeholder feedback introduces a critical new constraint: the system must support documentation updates at the pace of daily or multi-daily code releases, not the weekly/monthly cadence the current design assumes.

## What the Existing Repo Has That the Build Spec Confirms

These are areas where the repo and the build spec agree, and the repo's implementation is on the right track:

1. **Event-driven architecture via EventBridge.** Both use EventBridge for Git commit routing and downstream sync. The repo has config definitions; the build spec adds specific event patterns.

2. **DynamoDB dependency registry.** Both use DynamoDB for source-to-page mappings. The repo has two tables (SourceToPages, PageDependencies) with a RepositoryIndex GSI. The build spec uses a single-table design with page_id as partition key. The repo's two-table approach is actually better for bidirectional queries.

3. **Bedrock for generation.** Both use Claude on Bedrock. The repo has retry logic with exponential backoff.

4. **Gap flags / gap cards.** Both implement the concept of flagging content the agent can't resolve. The repo calls them `GapFlag` (field, reason, research_action). The build spec calls them "gap cards" with a richer schema (gap_type enum, source_file, source_line, JIRA ticket ID, status state machine). The build spec's version is more production-ready.

5. **Drift detection with severity classification.** Both implement severity levels. The repo uses critical/high/medium/low with rules based on change type and affected page count. The build spec uses High/Medium/Low. The repo's four-level system is more granular.

6. **YAML front-matter for dependency declarations.** Both use YAML front-matter. The repo's FrontMatter model has api_dependencies (with method-level granularity) and schema_dependencies (with version tracking). The build spec's schema is simpler (just repo + paths). The repo's model is richer.

7. **Human-in-the-loop enforcement.** Both require human approval before publication. The repo has `check_publication_gate()` and `check_approval_authorization()`. The build spec adds self-approval prevention and a two-writer review gate, which the repo doesn't have.

8. **Multi-surface publishing.** Both publish to developer portal, chatbot, MCP tools, onboarding. The repo has a Publisher class with per-surface status tracking.

## What the Build Spec Adds That the Repo Doesn't Have

1. **Two-writer peer review gate.** The build spec requires a Peer Review Queue where a second writer must approve before publish. The repo only checks that content_status is "approved" and approver_id is non-empty.

2. **Documentation Review Interface (two-panel).** The build spec defines a web UI with proposed draft (left) and current live page (right), amber/blue highlights, gap card panel, auto-save, keyboard navigation. The repo has DashboardAPI handlers but no actual UI.

3. **Governance Review Interface (three-panel).** The build spec defines a three-panel view (live page with stale fields in red, diff, pre-drafted correction). The repo has drift alerts but no correction-drafting or review UI.

4. **Governance Dashboard.** The build spec defines a catalog-card grid with confidence scores, staleness risk, and detection-to-publish cycle time. The repo has HealthMetrics functions but no dashboard UI.

5. **Slack notifications.** The build spec specifies Slack as the notification channel with structured block payloads. The repo uses SNS with a logging fallback.

6. **S3 as single canonical source with object metadata.** The build spec requires S3 objects to carry page_id, publish_timestamp, writer identities, confidence_score, staleness_risk as metadata. The repo stores drafts in S3 but doesn't use object metadata for governance.

7. **Audit log with append-only enforcement.** The build spec requires a DynamoDB resource-based policy denying UpdateItem and DeleteItem, plus 3-year S3 replication. The repo has an AuditTrail table but no append-only enforcement.

8. **WCAG 2.1 AA accessibility.** The build spec has specific accessibility requirements. The repo has no accessibility considerations.

9. **Acrolinx/Vale as automated quality gates.** The build spec requires these to run before the writer notification is sent. The repo has StyleChecker stubs but no real integration.

## What the Stakeholder Feedback Changes

The stakeholder feedback introduces a constraint that neither the existing repo nor the build spec fully addresses:

> "Sometimes we build features even within a day."
> "We will have capability to update our tools pretty fast (at least few times a week if not every day)."
> "Tech for docs and process need to evolve to be able to support faster tooling releases/updates."

This changes the design in three ways:

### 1. The 72-hour drift detection SLA is too slow

Both the repo and the build spec target 72-hour detection. The stakeholder is describing a world where code ships daily and tools decouple from the SDK by V0.24 (July 2026). At that cadence, 72 hours means documentation could be 3 releases behind before drift is even detected.

**Recommended change:** Add a "fast-track" detection mode that triggers on every npm publish event (not just Git commits). When a tool package publishes a new version, the system should detect affected docs within 1 hour, not 72. The 72-hour SLA remains for broader codebase drift; the fast-track handles high-velocity tool releases.

### 2. The 30-minute draft generation SLA may need a "hot path"

If tools update multiple times per week, the 30-minute generation SLA is fine for individual updates but the queue could back up. If 5 tool updates land in one day, the system needs to handle 5 concurrent generation jobs without degradation.

**Recommended change:** The build spec already specifies 10 concurrent generation jobs (NFR-001) and 50 concurrent jobs (NFR-003). These numbers should be validated against the stakeholder's cadence. Also consider a priority queue: tool-related changes get higher priority than general code changes.

### 3. The system needs to handle "agentic flow" outputs, not just human commits

The stakeholder mentions "fully agentic flows to fix bugs" and expects tools to be updated by agents, not humans. This means the system's input isn't just human Git commits; it's also agent-generated code changes that may arrive at machine speed.

**Recommended change:** Add an "agent commit" event type that the system recognizes and fast-tracks. When the commit author is an agent (identifiable by commit metadata or author email pattern), the system should: (a) auto-generate the draft without waiting for the standard EventBridge routing delay, (b) pre-populate the gap cards with the agent's own change description, and (c) route the draft directly to the assigned writer's Slack with a "fast-track review" label.

## What Should Change in the Existing Repo

### Priority 1: Wire the critical stubs

1. **Step Functions state machines.** The repo has individual Lambda handlers but no orchestration.
2. **Code_Amazon API client.** Source code fetching is stubbed.
3. **Real surface publishing.** Publisher has stub clients.
4. **Cognito enforcement.** Auth is configured but not enforced.

### Priority 2: Add the peer review workflow

The build spec's two-writer review gate is a hard requirement. Add:
- Peer Review Queue in DynamoDB
- Self-approval prevention (same Cognito identity check)
- Status state machine: draft -> pending_review -> changes_requested -> approved -> published

### Priority 3: Add fast-track detection for high-velocity releases

Per the stakeholder feedback:
- Add npm publish event listener (EventBridge rule for package registry events)
- Add 1-hour detection SLA for tool-related changes
- Add priority queue for generation jobs (tool changes > general code changes)
- Add "agent commit" recognition and fast-track routing

### Priority 4: Build the Writer Dashboard

The repo has API handlers but no UI. The build spec defines three views:
- Documentation Review Interface (two-panel)
- Governance Review Interface (three-panel)
- Governance Dashboard (catalog-card grid)

### Priority 5: Add tests and deployment automation

- Unit tests for all services
- Integration tests for the full pipelines
- CloudFormation/CDK templates for infrastructure provisioning

## What Should Change in the Build Spec

1. **Add fast-track detection mode.** The 72-hour SLA is insufficient for the stakeholder's use case. Add a 1-hour SLA for npm publish events and agent-generated commits.

2. **Add agent commit handling.** The build spec assumes human commits. Add an event type for agent-generated changes with fast-track routing.

3. **Add npm publish event source.** The EventBridge rules only match GitCommitPushed. Add a rule for package registry publish events.

4. **Revise the generation job priority model.** Add priority levels: P0 (tool release, agent commit), P1 (schema change), P2 (general code change). P0 jobs skip the standard queue.

5. **Add the "3 weeks to update docs" metric as a baseline.** The stakeholder explicitly says the current process takes 3 weeks. The build spec should cite this as the baseline and define the target: under 30 minutes for draft generation, under 4 hours for full review-to-publish cycle on fast-track items.

6. **Align the gap card schema with the repo's GapFlag model.** Merge both: keep the build spec's richer schema but add the repo's research_action field.

7. **Align the front-matter schema.** Use the repo's richer model with method-level api_dependencies and versioned schema_dependencies.

## Recommended Next Steps

1. **Update the input brief** (`input/tech_docs_integrator.yaml`) with the stakeholder feedback as business context. Add the "3 weeks to update docs" baseline, the "daily releases" cadence, and the "agentic flows" expectation.

2. **Re-run the pipeline** with the updated brief. The research agent should pick up the velocity constraint and the PRFAQ/BRD should reflect it.

3. **Merge the build spec's peer review workflow** into the existing repo as the next code sprint.

4. **Wire the Step Functions orchestration** as the second code sprint.

5. **Build the fast-track detection mode** as the third code sprint, directly addressing the stakeholder's concern about daily releases.
