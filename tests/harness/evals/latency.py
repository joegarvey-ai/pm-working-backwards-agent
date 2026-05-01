"""Latency budget eval assertions for the agent harness.

Each function accepts a RunRecord and raises AssertionError with a
descriptive message on failure.
"""

from __future__ import annotations

from tests.harness.models import RunRecord


def check_latency_budget(
    record: RunRecord,
    budgets: dict[str, float],
    total_budget: float,
) -> None:
    """Check per-task and total durations against latency budgets.

    Parameters
    ----------
    record:
        The RunRecord whose latency_summary is checked.
    budgets:
        Mapping of task name to maximum allowed duration in seconds.
    total_budget:
        Maximum allowed total run duration in seconds.

    Raises
    ------
    AssertionError
        * If a task name in *budgets* does not appear in the record's
          per_task latency data.
        * If any task's duration exceeds its budget.
        * If the total run duration exceeds *total_budget*.

        The error message lists every violation found.
    """
    errors: list[str] = []
    per_task = record.latency_summary.per_task

    # Check for missing tasks first.
    for task_name in budgets:
        if task_name not in per_task:
            errors.append(
                f"Task '{task_name}' in budget dict not found in latency trace"
            )

    # Check per-task budgets.
    for task_name, budget in budgets.items():
        actual = per_task.get(task_name)
        if actual is not None and actual > budget:
            errors.append(
                f"Task '{task_name}' exceeded budget: "
                f"{actual:.2f}s actual > {budget:.2f}s budget"
            )

    # Check total budget.
    total_actual = record.latency_summary.total_s
    if total_actual > total_budget:
        errors.append(
            f"Total run duration exceeded budget: "
            f"{total_actual:.2f}s actual > {total_budget:.2f}s budget"
        )

    if errors:
        raise AssertionError(
            "Latency budget exceeded:\n" + "\n".join(errors)
        )
