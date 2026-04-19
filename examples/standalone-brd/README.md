# Standalone BRD Mode (Agent 4 Only)

Use this mode when you already have an approved PRFAQ from another process and want to generate a BRD and build spec. Agents 1 and 2 are skipped entirely. You can optionally provide your own customer requirements file, which Agent 4 will reconcile against the PRFAQ.

## When to use this

- Your PRFAQ was written manually or in another tool and is already approved
- You want to regenerate the BRD without re-running research or PRFAQ generation
- You have pre-existing customer requirements (user stories, functional requirements) that should seed the BRD

## Commands

**Without customer requirements:**
```bash
pm_agent_system brd <input_file> --prfaq-path <prfaq_file>
```

**With customer requirements:**
```bash
pm_agent_system brd <input_file> --prfaq-path <prfaq_file> --requirements-path <requirements_file>
```

## Examples

The input file can be either the Obsidian-style markdown brief (recommended)
or YAML. Both forms of `example_input` ship with this folder.

```bash
# BRD from PRFAQ only (markdown input)
pm_agent_system brd examples/standalone-brd/example_input.md \
    --prfaq-path examples/standalone-brd/example_prfaq.md

# BRD from PRFAQ + customer requirements (CSV)
pm_agent_system brd examples/standalone-brd/example_input.md \
    --prfaq-path examples/standalone-brd/example_prfaq.md \
    --requirements-path examples/standalone-brd/example_requirements.csv

# BRD from PRFAQ + customer requirements (Markdown)
pm_agent_system brd examples/standalone-brd/example_input.md \
    --prfaq-path examples/standalone-brd/example_prfaq.md \
    --requirements-path examples/standalone-brd/example_requirements.md

# BRD from PRFAQ + an approved design brief (Agent 3 output)
pm_agent_system brd examples/standalone-brd/example_input.md \
    --prfaq-path examples/standalone-brd/example_prfaq.md \
    --design-brief-path output/design_brief_taskflow_v1.0.md
```

## Requirements file format

The requirements file should contain at minimum:
- **Title** — the requirement or user story name
- **Description** — what the requirement is about
- **Priority** — P0 through P4, or equivalent labels (must have, should have, etc.)

Supported formats: CSV, Excel (.xlsx/.xls), Markdown (.md), Word (.docx).

The parser is forgiving. Column headers are matched by partial keyword (e.g., a column called "Story Title" matches as title, "Requirement Detail" matches as description). Priority values are normalized to P0-P4 from common labels like "must have", "high", "critical", etc.

See `examples/templates/` for blank templates in CSV and Markdown formats.

## How requirements reconciliation works

When you provide a requirements file, Agent 4 does not blindly include them. It reconciles:

1. **Keeps** requirements that align with the PRFAQ, preserving your wording and priority
2. **Flags** requirements that contradict or aren't traceable to the PRFAQ
3. **Fills gaps** by generating requirements implied by the PRFAQ that your file doesn't cover
4. **Never overrides** your priority assignments (PM owns prioritization)

Every requirement in the BRD output has a `source` field: `customer_input`, `agent-generated`, or `reconciled`.

## Files in this example

| File | Purpose |
|---|---|
| `example_input.md` | Obsidian-style markdown input brief (recommended format) |
| `example_input.yaml` | Backward-compatible YAML version of the same brief |
| `example_prfaq.md` | A sample approved PRFAQ for TaskFlow |
| `example_requirements.csv` | 12 sample requirements in CSV format |
| `example_requirements.md` | Same requirements in Markdown table format |
