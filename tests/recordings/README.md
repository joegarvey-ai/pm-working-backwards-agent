# Golden Recordings

Baseline recordings for replay-based regression testing. Each file is a
`RunRecord` JSON produced by `tests/harness/run_crew()`.

## Available recordings

| File | Crew | LLM calls | Tool calls | Cost | Status |
|------|------|-----------|------------|------|--------|
| `research_baseline.json` | `research_crew` | 7 | 14 | $0.45 | Stable (replay OK) |
| `prfaq_baseline.json` | `research_and_generate_crew` | 10 | 17 | $0.76 | Stable (replay OK) |
| `full_pipeline_baseline.json` | `full_pipeline_crew` | 23 | 38 | $2.35 | Eval-only (replay limited) |

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

## Full pipeline recording: eval-only

The full pipeline recording was produced with `sequential_brd=True` which
eliminates the Bedrock toolResult interleaving race condition. It captures
all 9 task outputs and is usable for eval assertions:

```python
from tests.harness import load_record
from tests.harness.evals.quality import assert_no_banned_words
from tests.harness.evals.cost import check_cost_cap

record = load_record("tests/recordings/full_pipeline_baseline.json")
check_cost_cap(record, max_cost_usd=3.00)
assert_no_banned_words(record)
```

Full replay is not yet supported because CrewAI's structured output
converter makes additional LLM calls during validation retries that
the replay queue cannot predict. This is a known limitation tracked
for future work.

## Resolved production issues

1. **Bedrock toolResult interleaving** (resolved): Use `sequential_brd=True`
   to run BRD tasks sequentially instead of in parallel.

2. **BRDComplianceOutput validator** (resolved): The validator now
   auto-corrects contradictory LLM output instead of crashing.
