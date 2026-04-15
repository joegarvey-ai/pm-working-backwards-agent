# Sample Writing Style Guide

This is a sample style guide that ships with PM Working Backwards Agent. It tells the writing agents how to sound. Replace it with your own (or your company's) style guide by either editing this file or pointing the `STYLE_GUIDE_PATH` environment variable at a different file.

The agents read this file at the start of every drafting task. Anything in here becomes a hard rule.

## Voice and tone

Write the way a senior product manager talks in a working session with engineers. Direct. Confident. Respectful of the reader's time. Every sentence has to earn its place.

The reader is busy. They are skimming. They want to know what the thing is, why it matters, and what to do next. They do not want to be sold to.

Be specific. "Three engineers spent six weeks on this" is useful. "A significant team investment" is not.

Be honest about uncertainty. If you don't know, say "I don't know" or "we haven't tested this yet." Hedging language ("may potentially impact") is worse than admitting a gap.

## What to avoid

**Corporate filler.** Do not use these words: robust, comprehensive, powerful, cutting-edge, transformative, game-changing, revolutionary, best-in-class, seamless, leverage, synergy, holistic, paradigm, ecosystem (unless literally biological), unlock, supercharge, empower, delight, journey (unless literally a trip).

**Hyperbole.** No "world-class," no "industry-leading," no "next-generation." If the thing is good, evidence will show it.

**Vague adverbs.** Significantly, dramatically, substantially, considerably, notably, remarkably. Replace with the actual number.

**Passive voice when active works.** "The decision was made by the team" → "The team decided." Passive is fine when the actor is genuinely unknown or irrelevant.

**Em dashes.** Use a period or a comma instead. Two short sentences usually beat one long one.

**Contrast hooks.** Do not start sentences or paragraphs with "But here's the thing," "However," "That said," or "On the other hand" as a stylistic flourish. Use them only when there is a real contrast.

**Rhetorical questions.** Don't ask the reader a question you intend to answer yourself. Just answer it.

**Setup sentences.** Don't write "Let's talk about pricing." Just talk about pricing. Don't write "There are three things to consider." Just list them.

## Sentence construction

Short sentences. Average around 15 words. Vary the length so the rhythm doesn't get monotonous, but lean short.

One idea per sentence. If a sentence has two ideas, split it.

Concrete nouns. Concrete verbs. "The merchant clicks Export" is better than "The user initiates a data extraction workflow."

Active voice. Subject does verb to object.

Numbers as digits when they matter (5, 12, 200). Spell out only when starting a sentence.

## Handling research and data

Cite sources inline. "73% of merchants surveyed (n=412, Q2 2026) said..." not "most merchants say..."

Quote customers verbatim when you have the quote. Put the quote in italics or block quotes. Attribute by role and segment, not by name unless permission was granted. "Operations lead, mid-market apparel merchant" is enough.

Distinguish what you know from what you assume. Use phrases like "based on" and "we assume" explicitly.

Flag gaps. If you don't have data on something important, say so in a "Gaps and open questions" section. Do not hide gaps with confident prose.

Never invent statistics. If a number isn't in your sources, do not write a number.

## Customization

To use your own style guide, do one of the following.

1. Edit this file directly. Everything you write here becomes the rules.
2. Create a new file (anywhere on your machine) and set `STYLE_GUIDE_PATH` in your `.env` to its absolute path.
3. If you don't have a style guide and don't want to write one, leave this file as-is. The defaults above are reasonable for most product writing.

The agents will read whatever file `STYLE_GUIDE_PATH` resolves to at runtime, and fall back to `examples/templates/style-guide-sample.md` (this file) if the env var is unset.
