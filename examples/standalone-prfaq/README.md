# Standalone PRFAQ Mode (Agent 2 Only)

Use this mode when you already have your own research and just need help drafting the PRFAQ. Agent 1 (Research) is skipped entirely. Agent 2 reads your research file and uses it as the evidence base for the PRFAQ.

## When to use this

- You conducted your own market research, customer interviews, or competitive analysis
- You have research from another team or tool that you want to feed into the PRFAQ process
- You want to iterate on the PRFAQ without re-running research every time

## Command

```bash
pm_agent_system generate <input_file> --research-path <research_file>
```

## Example

```bash
pm_agent_system generate examples/standalone-prfaq/example_input.yaml \
    --research-path examples/standalone-prfaq/example_research.md
```

## Research file format

Your research file should be a markdown document with sections covering:

- **Market analysis** — sizing data, growth trends, TAM/SAM/SOM with sources
- **Competitive landscape** — 3+ competitors with positioning, strengths, weaknesses
- **Customer pain points** — evidence-backed pain points ranked by severity or frequency
- **Internal state assessment** — current architecture, team capacity, technical constraints

The agent is flexible about exact formatting. Include inline citations (`[source](url)`) wherever possible so the PRFAQ can carry them forward.

## Files in this example

| File | Purpose |
|---|---|
| `example_input.yaml` | The 8-field structured input for a fictional "TaskFlow" product |
| `example_research.md` | A sample manually-written research document for TaskFlow |
