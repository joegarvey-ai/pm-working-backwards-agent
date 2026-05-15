# Using PM Working Backwards with Claude Code

Claude Code is the recommended interface for running the PM Working Backwards pipeline. Instead of memorizing CLI commands, you describe your product idea conversationally and Claude Code handles structuring, execution, review, and iteration.

## Setup

1. Clone the repo and install dependencies:
```bash
git clone https://github.com/joegarvey-ai/pm-working-backwards-agent.git
cd pm-working-backwards-agent
uv sync
cp .env.example .env
```

2. Fill in `.env` with your keys:
```
LLM_PROVIDER=bedrock
AWS_BEARER_TOKEN_BEDROCK=<your-key>
AWS_BEDROCK_REGION=us-east-1
TAVILY_API_KEY=tvly-<your-key>
MODEL_ROUTING_ENABLED=true
```

3. Open the project in Claude Code. It reads `CLAUDE.md` automatically.

## How it works

Tell Claude Code your product idea in plain language. It will:

1. **Ask clarifying questions** to fill gaps in your thinking (customer, goals, constraints, success metrics)
2. **Draft a structured input brief** and show it to you for approval
3. **Run the pipeline stage by stage**, presenting each output for your review
4. **Handle revisions** conversationally (you say what to change, it re-runs)

You stay in control at every step. Claude Code does not execute the pipeline until you approve the input brief, and does not advance between stages without your explicit go-ahead.

## The conversational workflow

### Starting with an idea

You can start with anything from a single sentence to a detailed product concept:

> "I want to build a self-service analytics dashboard for our mid-market e-commerce merchants. They're stuck on weekly PDF reports and our support team is drowning in reporting tickets."

Claude Code will recognize this as a product idea and begin the intake process.

### Intake: filling the gaps

Before running any pipeline stage, Claude Code must establish a minimum-quality input brief. It will ask you about any gaps in these required areas:

| Area | What Claude Code needs | Example question it might ask |
|---|---|---|
| Feature summary | What the product does in one sentence | (usually provided in your initial description) |
| Target user | Who uses it, their context and constraints | "Who are the primary users? Are these merchants themselves or their ops teams?" |
| Goals | Measurable outcomes the product achieves | "What would success look like in 6 months? Any specific metrics?" |
| Success metrics | How you will know it worked | "How would you measure whether this reduced support tickets?" |
| Known constraints | Technical, business, or timeline limits | "Are there any platform constraints, compliance requirements, or timeline pressures?" |
| Business context | Current state numbers that ground the problem | "Do you have any data on current ticket volume, merchant adoption, or churn?" |

Claude Code should ask 3-5 focused questions, not a 20-question interview. If you provide a detailed initial description, it may only need 1-2 clarifications.

### Approval gate: the structured brief

After gathering enough context, Claude Code writes the structured input brief as a markdown file and presents it:

> "Here's the structured input brief I've drafted from our conversation. Please review it. I'll run the pipeline once you approve, or tell me what to change."

You read it, suggest changes, or approve. Claude Code writes the file to `input/` and proceeds.

### Stage-by-stage execution

Claude Code runs each pipeline stage individually (not `full-pipeline`), reads the output, and presents a conversational summary:

**Research stage:**
```bash
uv run pm_agent_system research input/my-product.md --skip-validation
```
> "The research brief is done. Key findings: the market is $25B growing at 20% CAGR, Triple Whale and Polar Analytics are the main competitors, and merchants cite real-time data access as their top unmet need. Want me to proceed to the PRFAQ, or would you like to adjust anything?"

**PRFAQ stage:**
```bash
uv run pm_agent_system generate input/my-product.md --skip-validation
```
> "The PRFAQ draft is ready. The press release leads with the 60% support ticket reduction claim. The internal FAQ addresses pricing, competitive positioning, and the build-vs-buy decision. Should I run the verification gate before we proceed to the BRD?"

**Verification (optional but recommended):**
```python
from pm_agent_system.verification import verify_stage
# Claude Code runs this and reports issues
```
> "The verification gate passed with 2 warnings: one em dash in the press release and a customer quote that's marked as placeholder since we don't have actual customer evidence yet. Want me to fix these before moving to BRD, or proceed as-is?"

**BRD stage:**
```bash
uv run pm_agent_system brd input/my-product.md --prfaq-path output/prfaq_*_v1.0.md
```

**Build spec stage:**
```bash
uv run pm_agent_system build-spec --brd-path output/brd_*_v1.0.md --target-tool kiro
```

### Revision

At any point, you can say things like:
- "Make the competitive section shorter"
- "Add a constraint about SOC 2 compliance"
- "The pricing in the BRD is wrong, we're targeting $49/month not $99"

Claude Code decides whether to revise the current artifact or re-run a stage, then executes the appropriate command.

## Rules for Claude Code

These rules ensure Claude Code behaves correctly when working in this project. They are embedded in `CLAUDE.md` but worth highlighting:

1. **Never auto-fill gaps in the input brief.** If the user hasn't described the customer, goals, or constraints, ask. Do not invent plausible-sounding details and proceed.

2. **Never run the pipeline without explicit user approval of the input brief.** Show the brief, get a "yes" or changes, then execute.

3. **Never auto-advance between stages.** After each stage completes, summarize the output and wait for the user to say "proceed" or give feedback.

4. **Run stages individually, not `full-pipeline`.** This keeps you in the loop between each artifact. Use `research`, then `generate`, then `brd`, then `build-spec` as separate commands.

5. **Disable `human_input` when running stages.** Add `--skip-validation` to avoid the CLI's interactive prompts (which conflict with Claude Code's own interaction model). Claude Code handles the review conversation instead.

6. **Present outputs as summaries, not raw text.** Read the output file and give a 3-5 sentence summary of what the artifact says. Offer to show the full text or specific sections if asked.

7. **When the user gives revision feedback, pick the right command.** Minor wording changes: use `revise`. Structural changes that affect downstream artifacts: re-run the stage. Scope changes (new constraint, different customer): update the input brief and re-run from that point.

8. **Run the verification gate when the user asks "is this ready?"** or between PRFAQ and BRD stages. Report issues conversationally.

## Quick reference: CLI commands

| Stage | Command |
|---|---|
| Research only | `uv run pm_agent_system research input/my-product.md --skip-validation` |
| Research + PRFAQ | `uv run pm_agent_system generate input/my-product.md --skip-validation` |
| BRD from PRFAQ | `uv run pm_agent_system brd input/my-product.md --prfaq-path output/prfaq_*_v1.0.md` |
| Build spec from BRD | `uv run pm_agent_system build-spec --brd-path output/brd_*_v1.0.md --target-tool kiro` |
| Revise PRFAQ | `uv run pm_agent_system revise --prfaq-path <file> --context-text "<feedback>"` |
| Revise BRD | `uv run pm_agent_system revise-brd --brd-path <file> --context-text "<feedback>"` |
| Trend report | `uv run python -m pm_agent_system.harness_trends --since 7d` |
| Trace visualization | `uv run python -m pm_agent_system.trace_export <recording.json>` |

## Tips

- Start your first conversation with just your product idea. Let Claude Code drive the structure.
- If you already have a detailed product doc, paste it in. Claude Code will extract what it needs and confirm with you.
- Use "run the verification gate" after PRFAQ to catch style issues before BRD.
- If a stage fails with a Bedrock token error, refresh your token in `.env` and tell Claude Code to retry.
- Output files appear in `./output/` and optionally in your Obsidian vault if configured.
