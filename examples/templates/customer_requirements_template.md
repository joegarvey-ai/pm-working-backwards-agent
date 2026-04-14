# Customer Requirements Template

Use this template to provide pre-existing customer requirements to the PM Agent System. Agent 3 will reconcile these against the approved PRFAQ when generating the BRD.

## Required elements per requirement

- **Title** — the requirement or user story name
- **Description** — what the requirement is about (user story format recommended)
- **Priority** — P0 through P4

## Option 1: Table format

| ID | Title | Description | Priority | Category | Notes |
|---|---|---|---|---|---|
| CR-001 | Example Requirement | As a [user type], I want to [action] so that [outcome] | P0 | Core Feature | Required for MVP launch |
| CR-002 | Another Requirement | Description of the requirement | P1 | Integration | |

## Option 2: Header + body format

If you prefer prose over tables, use markdown headers for each requirement:

### CR-001: Example Requirement

As a [user type], I want to [action] so that [outcome].

Priority: P0

This requirement is needed because [rationale].

### CR-002: Another Requirement

Description of the requirement.

Priority: P1

## Priority scale

| Priority | Label | Meaning |
|---|---|---|
| P0 | Must have | Required at launch. Product does not ship without this. |
| P1 | Should have | Expected at launch. Deferring requires explicit stakeholder sign-off. |
| P2 | Nice to have | Included if time permits. First candidates for post-launch iteration. |
| P3 | Future consideration | Not in scope for this release. Tracked for roadmap planning. |
| P4 | Backlog | Captured for completeness. No commitment to build. |

## Accepted formats

The parser accepts these file types:
- `.csv` — comma-separated with header row
- `.xlsx` / `.xls` — Excel spreadsheet (first sheet only)
- `.md` — Markdown (table or header+body format)
- `.docx` — Word document (tables or heading-based structure)

Column headers are matched flexibly. "Story Title" matches as title. "Requirement Detail" matches as description. "Importance" matches as priority.
