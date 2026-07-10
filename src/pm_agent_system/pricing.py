"""Anthropic API pricing constants.

Last verified: 2026-07-09 against https://www.anthropic.com/pricing
Update this file manually when pricing changes or when you switch models.
"""

# Prices are USD per 1 million tokens.
MODEL_PRICING = {
    # Current default: Claude Opus 4.8 (direct + Bedrock cross-region).
    "claude-opus-4-8": {
        "input_per_1m": 5.00,
        "output_per_1m": 25.00,
    },
    "us.anthropic.claude-opus-4-8": {
        "input_per_1m": 5.00,
        "output_per_1m": 25.00,
    },
    # Claude Sonnet 5 (routing sonnet tier).
    "claude-sonnet-5": {
        "input_per_1m": 3.00,
        "output_per_1m": 15.00,
    },
    "us.anthropic.claude-sonnet-5": {
        "input_per_1m": 3.00,
        "output_per_1m": 15.00,
    },
    # Claude Fable 5 (opt-in via ANTHROPIC_MODEL_ID=claude-fable-5).
    "claude-fable-5": {
        "input_per_1m": 10.00,
        "output_per_1m": 50.00,
    },
    # Claude Haiku 4.5 (routing haiku tier; judge model).
    "claude-haiku-4-5": {
        "input_per_1m": 1.00,
        "output_per_1m": 5.00,
    },
    "anthropic.claude-haiku-4-5-20251001-v1:0": {
        "input_per_1m": 1.00,
        "output_per_1m": 5.00,
    },
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": {
        "input_per_1m": 1.00,
        "output_per_1m": 5.00,
    },
    # Legacy ids retained so existing recordings/fixtures still price.
    "claude-sonnet-4-20250514": {
        "input_per_1m": 3.00,
        "output_per_1m": 15.00,
    },
    "us.anthropic.claude-sonnet-4-6": {
        "input_per_1m": 3.00,
        "output_per_1m": 15.00,
    },
    "global.anthropic.claude-sonnet-4-20250514-v1:0": {
        "input_per_1m": 3.00,
        "output_per_1m": 15.00,
    },
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return estimated cost in USD for a single Anthropic API call."""
    if model not in MODEL_PRICING:
        return 0.0
    rates = MODEL_PRICING[model]
    return (
        (input_tokens / 1_000_000) * rates["input_per_1m"]
        + (output_tokens / 1_000_000) * rates["output_per_1m"]
    )


def format_cost_summary(
    agent_usage: dict[str, dict[str, int]],
    model: str,
) -> str:
    """Format a CLI cost summary table from per-agent token usage.

    agent_usage: {agent_name: {"input_tokens": N, "output_tokens": N}}
    """
    lines = []
    total_cost = 0.0
    for name, usage in agent_usage.items():
        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)
        cost = estimate_cost(model, inp, out)
        total_cost += cost
        lines.append(f"  {name}:  {inp:,} in / {out:,} out  — est. ${cost:.2f}")

    lines.append(f"Total estimated cost: ${total_cost:.2f}")
    lines.append("")
    lines.append("Pricing last verified 2026-04-15. Actual billing may differ slightly.")
    return "\n".join(lines)
