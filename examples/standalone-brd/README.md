# Standalone BRD Mode (Agent 3 Only)

Use this mode when you already have an approved PRFAQ from another process and want to generate a BRD and build spec. Agents 1 and 2 are skipped entirely. You can optionally provide your own customer requirements file, which Agent 3 will reconcile against the PRFAQ.

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

```bash
# BRD from PRFAQ only
pm_agent_system brd examples/standalone-brd/example_input.yaml \
    --prfaq-path examples/standalone-brd/example_prfaq.md

# BRD from PRFAQ + customer requirements (CSV)
pm_agent_system brd examples/standalone-brd/example_input.yaml \
    --prfaq-path examples/standalone-brd/example_prfaq.md \
    --requirements-path examples/standalone-brd/example_requirements.csv

# BRD from PRFAQ + customer requirements (Markdown)
pm_agent_system brd examples/standalone-brd/example_input.yaml \
    --prfaq-path examples/standalone-brd/example_prfaq.md \
    --requirements-path examples/standalone-brd/example_requirements.md
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

When you provide a requirements file, Agent 3 does not blindly include them. It reconciles:

1. **Keeps** requirements that align with the PRFAQ, preserving your wording and priority
2. **Flags** requirements that contradict or aren't traceable to the PRFAQ
3. **Fills gaps** by generating requirements implied by the PRFAQ that your file doesn't cover
4. **Never overrides** your priority assignments (PM owns prioritization)

Every requirement in the BRD output has a `source` field: `customer_input`, `agent-generated`, or `reconciled`.

## Files in this example

| File | Purpose |
|---|---|
| `example_input.yaml` | The 8-field structured input for TaskFlow |
| `example_prfaq.md` | A sample approved PRFAQ for TaskFlow |
| `example_requirements.csv` | 12 sample requirements in CSV format |
| `example_requirements.md` | Same requirements in Markdown table format |
