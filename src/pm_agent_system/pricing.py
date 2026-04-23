"""Anthropic API pricing constants.

Last verified: 2026-04-15 against https://www.anthropic.com/pricing
Update this file manually when pricing changes or when you switch models.
"""

# Prices are USD per 1 million tokens.
MODEL_PRICING = {
    "claude-sonnet-4-20250514": {
        "input_per_1m": 3.00,
        "output_per_1m": 15.00,
    },
    # Bedrock inference profile IDs for Claude Sonnet 4.6.
    # Pricing is the same as direct Anthropic; AWS passes through the rate.
    "us.anthropic.claude-sonnet-4-6": {
        "input_per_1m": 3.00,
        "output_per_1m": 15.00,
    },
    "global.anthropic.claude-sonnet-4-20250514-v1:0": {
        "input_per_1m": 3.00,
        "output_per_1m": 15.00,
    },
    # Claude Haiku 4.5 (used for dev/testing, lower cost, faster).
    "anthropic.claude-haiku-4-5-20251001-v1:0": {
        "input_per_1m": 0.80,
        "output_per_1m": 4.00,
    },
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": {
        "input_per_1m": 0.80,
        "output_per_1m": 4.00,
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
