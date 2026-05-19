---
name: prfaq-agent
description: Write or revise a Working Backwards document (PRFAQ) for stakeholder alignment. Use when the PM needs a press release, FAQs, and customer experience narrative based on approved research.
---

# PRFAQ Agent

## What This Skill Does
Transforms approved research into a Working Backwards document (PRFAQ) that stakeholders can review for go/no-go decisions. Supports both initial generation and iterative revision based on stakeholder feedback.

## Key Files
- Agent prompt: #[[file:src/pm_agent_system/config/agents.yaml]] (prfaq_agent section)
- Task prompts: #[[file:src/pm_agent_system/config/tasks.yaml]] (generate_prfaq and revise_prfaq sections)
- Output schema: #[[file:src/pm_agent_system/models/prfaq_output.py]]
- Renderer: #[[file:src/pm_agent_system/utils/render_prfaq.py]]
- Style guide: #[[file:examples/templates/style-guide-sample.md]]

## Modes
- **Generate**: Create PRFAQ v1.0 from research findings
- **Revise**: Update specific sections based on stakeholder feedback. Preserves untouched sections.

## Running via CLI
```
# Generate (runs research first, then PRFAQ)
uv run pm_agent_system generate examples/input.yaml

# Revise an existing PRFAQ
uv run pm_agent_system revise --prfaq-path output/prfaq_foo_v1.0.md --context-text "Legal wants GDPR language"
uv run pm_agent_system revise --prfaq-path output/prfaq_foo_v1.0.md --context-path notes/feedback.md
```

## Output Structure
1. Press Release (future-state, 300-500 words, includes customer quote from research)
2. External FAQs (minimum 3, customer-facing)
3. Internal FAQs (minimum 5, stakeholder-facing, includes strategy using diagnosis/guiding-policy/coherent-actions framework)
4. Customer Experience Narrative (1-2 pages, present tense, third person, specific enough to sketch UI from)
5. Appendices (data points, competitor table, customer quotes, gaps)
6. Version History

## Style Rules
- Direct, confident voice
- No em dashes, no contrast hooks, no rhetorical question openers
- Claims backed by research data with citations
- Inverted pyramid structure
- Customer experience narrative must be specific, not vague

## For Revision Mode
- Read the current PRFAQ version and the feedback/notes provided
- Confirm which sections to revise before rewriting
- Update ONLY the specified sections
- Bump the version number

## Verification Gate (run after this skill produces output)
- The PRFAQ stage is the gated boundary: run `verify_stage(...)` from
  `src/pm_agent_system/verification.py` before starting the BRD stage
- Trigger automatically between PRFAQ and BRD; on user demand ("is this ready?");
  before publishing externally
- Report issues conversationally — em dashes, missing citations, contrast
  hooks, customer-evidence gaps — never paste raw verifier JSON
- If the user accepts warnings, log that they accepted; do not silently advance
