# Golden Recordings

Baseline recordings for replay-based regression testing. Each file is a
`RunRecord` JSON produced by `tests/harness/run_crew()`.

## Available recordings

| File | Crew | LLM calls | Tool calls | Cost | Status |
|------|------|-----------|------------|------|--------|
| `research_baseline.json` | `research_crew` | 8 | 17 | $0.51 | Stable |
| `prfaq_baseline.json` | `research_and_generate_crew` | 9 | 17 | $0.71 | Stable |
| `full_pipeline_baseline.json` | `full_pipeline_crew` | — | — | ~$1.50 | Blocked (see below) |

## How to regenerate

When prompts change intentionally, re-record baselines:

```python
import yaml
from tests.harness import run_crew
from pm_agent_system.crew import PmAgentSystem

with open("examples/input.yaml") as f:
    inputs = yaml.safe_load(f)

crew = PmAgentSystem().research_crew(skip_validation=True)
for t in crew.tasks:
    t.human_input = False

run_crew(crew, inputs, output_path="tests/recordings/research_baseline.json")
```

For `prfaq_baseline.json`, use `research_and_generate_crew(skip_validation=True)`.

For `full_pipeline_baseline.json`, use `full_pipeline_crew(skip_validation=True, skip_design=True)`
and add these template variables to inputs:

```python
inputs["prfaq_path"] = ""
inputs["research_path"] = ""
inputs["brd_path"] = ""
inputs["design_brief_path"] = ""
inputs["requirements_path"] = ""
inputs["target_tool"] = "kiro"
inputs["visual_style_guide_path"] = ""
inputs["context_path"] = ""
inputs["context_text"] = ""
```

## How to replay

```python
record = run_crew(crew, inputs, replay_path="tests/recordings/research_baseline.json")
```

Replay serves canned LLM and tool responses. No API calls are made. Completes in seconds.

## Full pipeline recording: blocked

The full pipeline recording fails intermittently due to two pre-existing issues
unrelated to the harness:

1. **Bedrock toolResult interleaving.** CrewAI's agent executor has a race
   condition where parallel async tasks (brd_structure, brd_cost_risk,
   brd_compliance) occasionally interleave tool-use/tool-result messages in
   the conversation history. Bedrock's Converse API requires strict pairing
   and rejects the request. Documented in `docs/recaps/2026-04-24_phase4a_research_parallelization.md`.

2. **BRDComplianceOutput validator contradiction.** The LLM sometimes sets
   `data_handling_gap_flag=True` while also populating `data_elements`,
   violating the mutual exclusivity constraint in the Pydantic model validator
   at `src/pm_agent_system/models/brd_intermediate.py:92-107`.

Both issues are non-deterministic (succeed ~50-70% of the time). The fix
belongs in the production code, not the harness. Tracked in the roadmap for
resolution after harness hardening is complete.
