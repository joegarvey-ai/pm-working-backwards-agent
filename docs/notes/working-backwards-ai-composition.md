# Working Backwards AI composition

How this pipeline composes with the internal **Working Backwards AI**
service (`workingbackwards.amazon.dev`) instead of re-implementing PRFAQ
persona critique.

## What Working Backwards AI is

An internal Amazon service that pressure-tests Working Backwards documents
through simulated customer personas (grounded in real VoC data) and named
domain-expert reviewers, including Senior Leader (VP/SVP scrutiny) and
Responsible AI. It reached MCP availability in 2026, so an external agent
can invoke it programmatically rather than a human using the web app.

## Why compose rather than build

The pipeline already generates a strong first-draft PRFAG. What it cannot
do well is adversarial critique from many stakeholder viewpoints, which is
exactly Working Backwards AI's job and is backed by data this repo does not
have. Re-implementing that locally would be lower quality and duplicate a
tool with a large internal user base. So the PRFAQ agent calls Working
Backwards AI as a reviewer and folds the critique into its draft.

## How it is wired

- Tool: `src/pm_agent_system/tools/working_backwards_ai.py`
  (`WorkingBackwardsAICritiqueTool`).
- Transport: stdio via an MCP Gateway client binary, mirroring
  `builder_mcp`. Binary name defaults to `wb-ai-mcp`, override with
  `WB_AI_MCP_BINARY`; remote tool defaults to `ask_wbai`, override with
  `WB_AI_MCP_TOOL`. Midway auth is handled by the binary.
- Gate: `crew._wb_ai_enabled()` checks the binary is on PATH. Absent
  outside Amazon, so the tool stays unregistered there and the pipeline
  runs unchanged.
- Attachment: added to `prfaq_agent` only. Its backstory instructs the
  agent to critique its completed draft once, fold in the substantive
  points, and record unaddressed points in `appendix_gaps`.

## Design constraints honored

- **Transparent relay.** Working Backwards AI owns its coaching logic, so
  the tool forwards the draft verbatim and returns the critique verbatim.
  It does not paraphrase, pre-filter, or interpret the exchange.
- **Single-shot, not multi-turn.** Working Backwards AI is a stateful,
  multi-turn coach; this pipeline is a batch generator with human
  checkpoints. The tool issues one critique request per call. Iterative
  multi-turn refinement stays a human activity in the web app.
- **Reviewer, not author.** The critique informs a revision; it never
  becomes PRFAQ content, and it does not replace the human review
  checkpoint.

## Open items (need a live endpoint to verify)

Not runtime-verifiable from a machine without Midway and the MCP Gateway
client. Before relying on it, run one live smoke test and confirm:

1. The registered remote tool name (`ask_wbai` assumed) and its argument
   contract (this tool sends `{"prompt": ...}`). Adjust `WB_AI_MCP_TOOL`
   and the argument shape in `working_backwards_ai.py` if they differ.
2. The MCP Gateway client binary name on the host (set `WB_AI_MCP_BINARY`).
3. Response shape: the tool concatenates text content blocks via
   `_mcp_stdio._extract_text`; confirm the service returns text content.
4. Latency: the tool uses a 120s timeout (persona critique is slower than
   a search). Tune if needed.

Unit tests (`tests/tools/test_working_backwards_ai.py`) cover the relay,
lens handling, guards, and logging with the transport mocked; they do not
exercise the live service.
