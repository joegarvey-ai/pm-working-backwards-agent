# PRFAQ Save Bug — Root Cause

**Date:** 2026-04-15
**Fixed in:** Issue 1.1 (PIP Sprint 1)

## Root Cause

The `cmd_full_pipeline` function in `main.py` extracted and saved `BRDOutput` and `CodingPromptOutput` from the crew's `tasks_output`, but never extracted or saved `PRFAQOutput`. The standalone `cmd_generate` command did save the PRFAQ because it was the final task output, extracted directly via `extract_pydantic_output`. In the full pipeline, the PRFAQ is an intermediate result (not the final output), so it had to be found by iterating `tasks_output` — which was only done for `BRDOutput`.

The same gap existed for `ResearchOutput` — the research brief was also not saved to disk during a full-pipeline run. Both were fixed by adding extraction loops matching the existing `BRDOutput` pattern.

Kiro's `default_factory=list` commit (`6e45c1c`) was not the direct cause of the save failure, though it was suspected. The bug predated the defaults change — the save logic was simply never written for the full-pipeline path.
