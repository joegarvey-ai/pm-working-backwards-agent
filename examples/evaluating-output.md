# Evaluating Agent Output

A quick checklist for reviewing what the agents produce. If an output fails these checks, re-run with more specific input or use the `revise` commands.

## Research Brief

- Are there at least 3 competitors with named sources? If fewer, the agent flagged a gap. Check the Gaps section.
- Does every factual claim have an inline `[source](url)` citation? Uncited claims are unreliable.
- Is the Gaps and Limitations section honest? A brief with no gaps is suspicious. Every research run has blind spots.
- Are customer quotes attributed to a real source (G2, Capterra, Dovetail)? Quotes without attribution may be fabricated.

## PRFAQ

- Is the press release 300-500 words? Shorter means it's thin. Longer means it's rambling.
- Does the customer experience narrative have enough detail that a designer could sketch the screens? If it says "intuitive interface" without describing what the user sees, it's too vague.
- Are the internal FAQs hard questions? Look for a strategy question (diagnosis / guiding policy / coherent actions) and a risk question that surfaces real gaps. Softball FAQs are a sign the agent didn't push hard enough.
- Does the appendix_gaps section carry forward gaps from the research? If the research had open questions, they should appear here too.

## BRD

- Do all functional requirements have given/when/then acceptance criteria? Requirements without testable criteria are ambiguous.
- Are there Mermaid diagrams in both the proposed solution overview and the technical context section? Missing diagrams mean the agent skipped architectural thinking.
- Do cost flags have real reference URLs (not invented ones)? Click a few to verify.
- Does every user story trace to a PRFAQ section or research finding? Untraced stories may be hallucinated.

## Build Spec

- Do the acceptance criteria in the build spec match the BRD exactly? Compare a few side by side. If they're paraphrased, the agent violated its instructions.
- Is the out-of-scope section populated? If it's empty, P2 items may have leaked into the build.
- Does the formatted_spec match your target tool's expected format? Open it in Kiro, Claude Code, Cursor, or Lovable and confirm it parses correctly.
