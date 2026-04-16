"""Unit tests for the pricing module."""

from pm_agent_system.pricing import estimate_cost, format_cost_summary


def test_known_model_returns_correct_cost():
    """Hand-calculated: 1000 input @ $3/1M = $0.003, 2000 output @ $15/1M = $0.03."""
    cost = estimate_cost("claude-sonnet-4-20250514", input_tokens=1000, output_tokens=2000)
    expected = (1000 / 1_000_000) * 3.00 + (2000 / 1_000_000) * 15.00
    assert abs(cost - expected) < 1e-10


def test_unknown_model_returns_zero():
    cost = estimate_cost("unknown-model", input_tokens=5000, output_tokens=5000)
    assert cost == 0.0


def test_zero_tokens_return_zero():
    cost = estimate_cost("claude-sonnet-4-20250514", input_tokens=0, output_tokens=0)
    assert cost == 0.0


def test_format_cost_summary_includes_all_agents():
    usage = {
        "Research Agent": {"input_tokens": 1240, "output_tokens": 3820},
        "PRFAQ Agent": {"input_tokens": 4100, "output_tokens": 9200},
    }
    summary = format_cost_summary(usage, "claude-sonnet-4-20250514")
    assert "Research Agent" in summary
    assert "PRFAQ Agent" in summary
    assert "Total estimated cost" in summary
    assert "Pricing last verified" in summary
