# Troubleshooting

## Incomplete Output Warning

If you see a warning block at the top of an artifact like:

> **Warning: Incomplete output detected.** The following sections were not generated...

This means one or more sections in the artifact are empty even though the model was expected to fill them. The most common cause is **output truncation**: the model ran out of its `max_tokens` budget before finishing the full response, and Pydantic filled in empty defaults for the remaining fields.

### Remediation

1. **Check token usage.** If a `.checkpoint.json` file exists in `output/`, look at the `tokens_out` value for the affected agent. If it is close to the `max_tokens` limit (currently 16,384 for PRFAQ and BRD agents), truncation is the likely cause.

2. **Re-run the affected agent.** If the pipeline crashed mid-run, use `--resume` to re-run only the failing agent:
   ```
   uv run pm_agent_system full-pipeline examples/input.yaml --resume
   ```

3. **Increase max_tokens.** If truncation is persistent, increase the `_LARGE_MAX_TOKENS` value in `src/pm_agent_system/crew.py`. Note that higher limits increase per-run cost.

4. **Simplify the input.** Very broad or complex inputs can produce outputs that exceed token limits. Consider narrowing the scope of the feature summary or goals.

### Why defaults exist

Pydantic output models use `default_factory=list` and `default=""` on optional sections so that a truncated response still produces a valid (if incomplete) model instead of crashing the pipeline. The warning block surfaces this tradeoff so you know when an artifact needs attention.
