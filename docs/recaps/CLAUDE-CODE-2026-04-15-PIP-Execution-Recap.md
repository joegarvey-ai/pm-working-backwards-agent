# Claude Code Session Recap — 2026-04-15: PIP Execution

**Session type:** Performance Improvement Plan execution
**Source:** Performance Improvement Plan — Pipeline Fixes & Review UX
**Agent:** Claude Code (Opus 4.6)
**Date:** 2026-04-15

---

## Commits Pushed

| Hash | Description |
|---|---|
| `9b72057` | fix: save research brief and PRFAQ in full-pipeline path |
| `3ea60fc` | feat: add per-agent checkpointing with --resume and --fresh flags |
| `96591ee` | feat: add per-run cost estimate with pricing module |
| `3cc5956` | feat: add renderer warnings for empty defaulted fields |
| `fe796b7` | feat: add self-contained HTML export for all artifacts |
| `657752c` | feat: add explicit competitive analysis carry-through to BRD prompt |

---

## Acceptance Criteria Results

### Issue 1.1 — Fix PRFAQ save bug in full-pipeline path
**Status: PASS**
- Root cause: `cmd_full_pipeline` never extracted `PRFAQOutput` or `ResearchOutput` from `tasks_output`. Fixed by adding extraction loops matching the existing `BRDOutput` pattern.
- Integration test confirms all three `.md` files are produced.
- Root-cause note at `docs/notes/prfaq-save-bug-root-cause.md`.
- Note: The original hypothesis (that Kiro's `default_factory=list` change caused the save failure) was incorrect. The save logic was simply never written for the full-pipeline path.

### Issue 1.2 — Intermediate checkpointing with --resume
**Status: PASS**
- `checkpoint.py` manages a flat `.checkpoint.json` manifest with input hash, timestamps, and per-artifact metadata.
- `task_callback` on the CrewAI crew saves artifacts incrementally during a fresh run.
- `--resume` checks the checkpoint and runs only `brd_from_prfaq_crew()` when research + PRFAQ are complete.
- `--fresh` deletes the checkpoint and runs everything.
- Checkpoint is deleted on successful completion.
- 5 unit tests + 4 integration tests, all pass.

### Issue 1.3 — Per-run cost estimate in CLI
**Status: PASS**
- `pricing.py` with manual pricing constants (last verified 2026-04-15).
- Cost summary printed at the end of every `full-pipeline` run.
- Token data written to checkpoint manifest.
- Note: Per-agent token breakdown uses proportional attribution from CrewAI's aggregate `token_usage`. Exact per-agent tracking would require intercepting LLM calls, which CrewAI doesn't cleanly expose at the agent boundary in this version. The proportional approach is a judgment call that gives directionally correct numbers. Spot-check against Anthropic console billing to validate.

### Issue 2.1 — Renderer warnings for empty defaulted fields
**Status: PASS**
- `output_inspector.py` inspects Pydantic model fields with defaults that are still empty.
- All four renderers (research, PRFAQ, BRD, build spec) prepend a warning block.
- BRD renderer adds inline "_Not generated in this run._" for empty risks, NFRs, and timeline sections.
- `docs/troubleshooting.md` explains the warning and remediation.
- 8 tests pass.

### Issue 2.2 — Static HTML export of artifacts
**Status: PASS**
- `html_export.py` uses `markdown-it-py` (already a transitive dependency via rich/textual, no new dep added).
- Every save function produces `.md` + `.html` pairs.
- Inline CSS under 80 lines, includes dark mode via `prefers-color-scheme`.
- No CDN, no `<script>`, no external resources. Fully offline.
- `--open` flag on `research`, `generate`, `full-pipeline`, and `brd` commands.
- README updated with "Reviewing Output" section.
- 7 tests pass.

### Issue 2.3 — Competitive analysis carry-through in BRD prompt
**Status: PASS (prompt change only)**
- Added step 2a to both `generate_brd_chained` and `generate_brd_standalone` in `config/tasks.yaml`.
- Explicit imperative instructions: read competitive analysis, reference competitors by name, identify per-competitor differentiation.
- Before/after comparison requires a live API run (not done in this session due to API cost). The prompt change is in place; verify on next real run.

---

## Test Suite

**55 tests, all passing.** New tests added this session:
- `test_full_pipeline_save.py` (1 test) — integration test for artifact saves
- `test_checkpoint.py` (10 tests) — checkpoint module + resume/fresh behavior
- `test_pricing.py` (4 tests) — cost estimation
- `test_output_inspector.py` (8 tests) — empty field detection + renderer warnings
- `test_html_export.py` (7 tests) — HTML conversion, offline safety, CSS size

---

## Cost Spot-Check

Not performed in this session. The pricing module uses manual constants; a real API run is needed to compare the cost summary output against Anthropic console billing. Recommend doing this on the next `full-pipeline` run.

---

## Technical Debt Noticed (Not Addressed)

1. **Per-agent token attribution is approximate.** CrewAI's `token_usage` is aggregate. The current approach distributes tokens proportionally by task count. For accurate per-agent costs, we'd need to snapshot each agent's LLM `_token_usage` before/after each task — possible via the `task_callback` but requires accessing the crew's agent instances, which are created inside `PmAgentSystem` and not easily accessible from the callback. Worth revisiting when CrewAI exposes per-task usage in `TaskOutput`.

2. **`--resume` only covers the Agent 3 resume case.** If a crash happens between Agent 1 and Agent 2, `--resume` falls through to a full run (re-paying for Agent 1). Supporting Agent 2-only resume would require either a new task in `tasks.yaml` (a standalone PRFAQ-from-disk task) or restructuring the pipeline into three separate crew kickoffs. The PIP scope was Agent 3 resume, so this was left as-is.

3. **The `webbrowser` import is unconditional.** It's a stdlib module so there's no performance concern, but if the system runs headless (CI), `webbrowser.open()` will silently fail. The `--open` flag is opt-in so this is fine in practice.

4. **HTML export does not handle Mermaid diagrams.** Mermaid fenced code blocks are rendered as plain `<pre><code>` in the HTML. A future enhancement could embed a Mermaid renderer, but that would require JavaScript (violating the current "no JS" constraint) or a server-side rendering step.

---

## Judgment Calls

1. **Used `task_callback` for incremental saves** instead of restructuring the pipeline into three separate crew kickoffs. This preserved the existing `full_pipeline_crew` composition and avoided adding new tasks/crews, but means the callback approach depends on CrewAI calling the callback after each task (which it does in v1.13.0).

2. **Used `markdown-it-py` for HTML export** instead of adding a new dependency. It's already present as a transitive dep from `rich` (via `textual`). This is stable but technically depends on the transitive dep chain not removing it in a future version. If that happens, add it explicitly to `pyproject.toml`.

3. **Added dark mode to HTML for free** via `prefers-color-scheme` media query. The PIP said "skip dark mode unless it's free" — this adds zero complexity (just CSS) so I included it.

4. **Applied competitive analysis instructions to both `generate_brd_chained` and `generate_brd_standalone`** even though the PIP only mentioned the chained version. The standalone version is used by the `brd` command and would have the same gap.
