---
inclusion: always
name: product-context
description: PM Working Backwards Agent - product overview and conventions
---

# PM Working Backwards Agent

This project is a multi-agent AI system that takes a product problem statement and produces research-backed PM artifacts: market research → PRFAQ (Working Backwards document) → BRD → build specification.

## Core Principles
- Every factual claim must trace to a research source
- AWS services are the default for all technical architecture
- Human reviews and approves each artifact before the next generates
- No hyperbole, no corporate filler, no unsourced claims
- Requirements use "The system shall..." format with given/when/then acceptance criteria

## Pipeline Flow
1. PM provides structured input (7 fields + optional business context)
2. Agent 1 (Research): Tavily search + internal docs + Dovetail → ResearchOutput
3. Agent 2 (PRFAQ): Working Backwards document with press release, FAQs, customer experience narrative
4. Agent 3 (BRD + Build Spec): Requirements with code samples, then tool-specific build spec

## Style Rules
- No em dashes as punctuation
- No contrast hooks ("It's not X — it's Y")
- No rhetorical questions as section openers
- Inverted pyramid: lead with the claim, follow with support
- One idea per paragraph
