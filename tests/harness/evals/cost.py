"""Cost cap eval assertions for the agent harness.

Each function accepts a RunRecord and raises AssertionError with a
descriptive message on failure.
"""

from __future__ import annotations

from tests.harness.models import RunRecord


def check_cost_cap(record: RunRecord, max_cost_usd: float) -> None:
    """Raise AssertionError if total cost exceeds *max_cost_usd*.

    Parameters
    ----------
    record:
        The RunRecord whose cost_summary is checked.
    max_cost_usd:
        Maximum allowed total cost in USD.

    Raises
    ------
    AssertionError
        If the total estimated cost exceeds the cap.  The message
        includes both the cap and the actual cost.
    """
    actual = record.cost_summary.total_usd
    if actual > max_cost_usd:
        raise AssertionError(
            f"Total cost exceeded cap: "
            f"${actual:.4f} actual > ${max_cost_usd:.4f} cap"
        )


def check_per_agent_cost_cap(
    record: RunRecord,
    caps: dict[str, float],
) -> None:
    """Raise AssertionError listing each agent that exceeded its cost cap.

    Parameters
    ----------
    record:
        The RunRecord whose cost_summary is checked.
    caps:
        Mapping of agent name to maximum allowed cost in USD.

    Raises
    ------
    AssertionError
        If any agent's estimated cost exceeds its cap.  The message
        lists every agent that exceeded, with the cap and actual values.
    """
    errors: list[str] = []
    per_agent = record.cost_summary.per_agent

    for agent_name, cap in caps.items():
        actual = per_agent.get(agent_name, 0.0)
        if actual > cap:
            errors.append(
                f"Agent '{agent_name}' exceeded cost cap: "
                f"${actual:.4f} actual > ${cap:.4f} cap"
            )

    if errors:
        raise AssertionError(
            "Per-agent cost cap exceeded:\n" + "\n".join(errors)
        )
