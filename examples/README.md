# Examples

This directory contains a complete sample run of PM Working Backwards Agent on a fictional e-commerce analytics dashboard. Read these files to see what the agents produce before you run the system on your own problem.

## Files

| File | What it is |
|---|---|
| `input.yaml` | The starting input. A short problem statement, goals, target users, success metrics, and constraints. This is what you'd write to kick off a run. |
| `research_brief.md` | What Agent 1 (Research) produces. Market sizing, competitive landscape, customer evidence, gaps and open questions. |
| `prfaq_v1.0.md` | What Agent 2 (PRFAQ) produces from the research brief. A Working Backwards press release, FAQ, and customer quotes. |
| `brd_v1.0.md` | What Agent 3 (BRD) produces from the approved PRFAQ. Functional requirements, non-functional requirements, scope boundaries, dependencies. |
| `build_spec_kiro_formatted.md` | What Agent 4 (Build Spec) produces from the BRD. A Kiro-formatted spec ready to drop into a coding agent. |

## How to use these examples

1. Read `input.yaml` to see the format. It is short and PM-friendly. No technical knowledge required.
2. Read `research_brief.md` to see what evidence-gathering looks like. Note the source attribution and the explicit "Gaps" section.
3. Read `prfaq_v1.0.md` to see how the research becomes a stakeholder-ready Working Backwards document.
4. Read `brd_v1.0.md` and `build_spec_kiro_formatted.md` to see the handoff to engineering.

The content is synthetic. The numbers, quotes, and company names are illustrative, not real research. Use the structure as a template for what your own runs should look like.

## Running on your own input

Copy `input.yaml` to a new file, replace the contents with your own product problem, and run:

```bash
uv run pm_agent_system full --input path/to/your-input.yaml
```

See `../SETUP.md` for full setup instructions and `../README.md` for the CLI reference.
