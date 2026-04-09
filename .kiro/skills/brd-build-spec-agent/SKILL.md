---
name: brd-build-spec-agent
description: Produce an engineer-ready BRD and a coding tool build spec from an approved PRFAQ. Use when the PM has stakeholder alignment and needs requirements plus a build-ready specification.
---

# BRD + Build Spec Agent

## What This Skill Does
Takes the approved PRFAQ and research, produces a 12-section BRD with code samples and Mermaid diagrams, then generates a build specification formatted for the PM's chosen coding tool.

## BRD Output (12 sections)
1. Executive Summary
2. Problem Statement
3. Proposed Solution Overview (with Mermaid architecture diagram)
4. User Stories (As a... I want... So that... with P0/P1/P2 priority)
5. Functional Requirements (FR-001 format, "The system shall...", given/when/then, code samples)
6. Non-Functional Requirements (performance, security, scalability, accessibility, compliance)
7. Technical Context and Dependencies (current state + Mermaid diagram)
8. Cost-Relevant Decisions (flags, not estimates - with reference URLs)
9. Risks and Mitigations
10. Success Metrics (current state -> target state -> measurement method)
11. Timeline and Milestones
12. Version History

## Build Spec Targets
- **Kiro**: Spec-driven format (requirements -> design -> tasks)
- **Claude Code**: Structured markdown prompt
- **Cursor**: Composer-ready markdown
- **Lovable**: Natural language Agent Mode prompt

## Key Rules
- AWS services by default for all architecture
- Acceptance criteria carry forward from BRD to build spec EXACTLY - no paraphrasing
- Code samples show canonical patterns (API contracts, data models, Mermaid diagrams)
- Cost flags identify decisions with cost implications, never estimate dollar amounts
- No ambiguous language: "fast" needs a latency target, "intuitive" needs a metric
