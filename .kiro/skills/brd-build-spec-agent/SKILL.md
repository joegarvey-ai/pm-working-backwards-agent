---
name: brd-build-spec-agent
description: Produce an engineer-ready BRD and a coding tool build spec from an approved PRFAQ. Use when the PM has stakeholder alignment and needs requirements plus a build-ready specification.
---

# BRD + Build Spec Agent

## What This Skill Does
Takes the approved PRFAQ and research, produces a 12-section BRD with code samples and Mermaid diagrams, then generates a build specification formatted for the PM's chosen coding tool.

## Key Files
- Agent prompt: #[[file:src/pm_agent_system/config/agents.yaml]] (brd_agent section)
- Task prompts: #[[file:src/pm_agent_system/config/tasks.yaml]] (generate_brd_chained, generate_brd_standalone, revise_brd, generate_build_spec_chained, generate_build_spec_standalone sections)
- BRD output schema: #[[file:src/pm_agent_system/models/brd_output.py]]
- Build spec output schema: #[[file:src/pm_agent_system/models/coding_prompt_output.py]]
- BRD renderer: #[[file:src/pm_agent_system/utils/render_brd.py]]
- Build spec renderer: #[[file:src/pm_agent_system/utils/render_build_spec.py]]
- Example Kiro-formatted build spec: #[[file:examples/build_spec_kiro_formatted.md]]

## Running via CLI
```
# Full pipeline (research + PRFAQ + BRD + build spec)
uv run pm_agent_system full-pipeline examples/input.yaml --target-tool kiro

# BRD from approved PRFAQ
uv run pm_agent_system brd examples/input.yaml --prfaq-path output/prfaq_foo_v1.0.md

# Regenerate build spec from approved BRD
uv run pm_agent_system build-spec --brd-path output/brd_foo_v1.0.md --target-tool kiro

# Revise existing BRD
uv run pm_agent_system revise-brd --brd-path output/brd_foo_v1.0.md --context-text "Add GDPR requirements"
```

## BRD Output (12 sections)
1. Executive Summary
2. Problem Statement
3. Proposed Solution Overview (with Mermaid architecture diagram)
4. User Stories (As a... I want... So that... with P0/P1/P2 priority)
5. Functional Requirements (FR-001 format, "The system shall...", given/when/then, code samples)
6. Non-Functional Requirements (performance, security, scalability, accessibility, compliance)
7. Technical Context and Dependencies (current state + Mermaid diagram)
8. Cost-Relevant Decisions (flags with AWS pricing data, not dollar estimates)
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
- Acceptance criteria carry forward from BRD to build spec EXACTLY, no paraphrasing
- Code samples show canonical patterns (API contracts, data models, Mermaid diagrams)
- Cost flags identify decisions with cost implications, never estimate dollar amounts
- No ambiguous language: "fast" needs a latency target, "intuitive" needs a metric
