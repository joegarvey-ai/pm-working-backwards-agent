"""Cost and run-metrics reporting.

Extracted from ``main.py`` (audit item #16). Turns a CrewAI result's token
usage into a per-agent cost summary, prints it, persists per-artifact token
data into the resume checkpoint, and appends a run record to the usage log.
"""

from __future__ import annotations

from datetime import datetime

from pm_agent_system.checkpoint import save_checkpoint
from pm_agent_system.crew import _MODEL
from pm_agent_system.io_layer import _append_usage_log, _output_dir
from pm_agent_system.pricing import estimate_cost, format_cost_summary


def _extract_agent_usage(result) -> dict[str, dict[str, int]]:
    """Extract per-agent token usage from a CrewOutput result.

    Uses the aggregate token_usage from CrewAI and attributes it across agents
    based on which agents were in the crew. Falls back to aggregate if per-agent
    data is not available.
    """
    usage = {}
    token_usage = getattr(result, "token_usage", None)
    if token_usage is None:
        return usage

    prompt = getattr(token_usage, "prompt_tokens", 0)
    completion = getattr(token_usage, "completion_tokens", 0)

    # If we can't break down per-agent, report the aggregate
    if prompt == 0 and completion == 0:
        return usage

    # Map task outputs to agent names based on the Pydantic output type
    agent_map = {
        "ResearchOutput": "Research Agent",
        "PRFAQOutput": "PRFAQ Agent",
        "DesignBriefOutput": "Design Brief Agent",
        "BRDOutput": "BRD Agent",
        "CodingPromptOutput": "BRD Agent",  # build spec runs on the same agent
        "FeedbackClassification": "Feedback Classifier",  # TD8
    }

    # Count how many tasks each agent ran
    agent_task_counts: dict[str, int] = {}
    if hasattr(result, "tasks_output"):
        for to in result.tasks_output:
            if hasattr(to, "pydantic") and to.pydantic is not None:
                type_name = type(to.pydantic).__name__
                agent_name = agent_map.get(type_name, "Unknown")
                agent_task_counts[agent_name] = agent_task_counts.get(agent_name, 0) + 1

    if not agent_task_counts:
        # Fallback: report aggregate under a single entry
        usage["Pipeline Total"] = {"input_tokens": prompt, "output_tokens": completion}
        return usage

    # Distribute tokens proportionally by task count (rough approximation)
    total_tasks = sum(agent_task_counts.values())
    for agent_name, count in agent_task_counts.items():
        fraction = count / total_tasks
        usage[agent_name] = {
            "input_tokens": int(prompt * fraction),
            "output_tokens": int(completion * fraction),
        }

    return usage


def _print_cost_summary(result, checkpoint, output_dir):
    """Print a cost summary and update checkpoint with token data."""
    agent_usage = _extract_agent_usage(result)
    if not agent_usage:
        return

    # Merge with prior checkpoint usage (for resumed runs)
    for artifact_name, info in checkpoint.get("artifacts", {}).items():
        if info.get("tokens_in", 0) > 0 or info.get("tokens_out", 0) > 0:
            # Prior agent costs already recorded; they'll show in the checkpoint
            pass

    print("\nPipeline complete.")
    print(format_cost_summary(agent_usage, _MODEL))

    # Update checkpoint with token data for each artifact
    for agent_name, usage in agent_usage.items():
        cost = estimate_cost(_MODEL, usage["input_tokens"], usage["output_tokens"])
        # Find the matching artifact name
        artifact_key = {
            "Research Agent": "research_brief",
            "PRFAQ Agent": "prfaq",
            "Design Brief Agent": "design_brief",
            "BRD Agent": "brd",
        }.get(agent_name)
        if artifact_key and artifact_key in checkpoint.get("artifacts", {}):
            checkpoint["artifacts"][artifact_key]["tokens_in"] = usage["input_tokens"]
            checkpoint["artifacts"][artifact_key]["tokens_out"] = usage["output_tokens"]
            checkpoint["artifacts"][artifact_key]["estimated_cost_usd"] = round(cost, 4)
    save_checkpoint(output_dir, checkpoint)


def _print_run_metrics(result, command: str, elapsed_seconds: float, product_slug: str = "") -> None:
    """Print cost summary and log run metrics to JSONL for any command."""
    agent_usage = _extract_agent_usage(result)
    if agent_usage:
        print(format_cost_summary(agent_usage, _MODEL))

    total_in = sum(u.get("input_tokens", 0) for u in agent_usage.values())
    total_out = sum(u.get("output_tokens", 0) for u in agent_usage.values())
    total_cost = estimate_cost(_MODEL, total_in, total_out)

    print(f"Elapsed: {elapsed_seconds:.1f}s")

    # Append to JSONL log
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "command": command,
        "model": _MODEL,
        "input_tokens": total_in,
        "output_tokens": total_out,
        "estimated_cost_usd": round(total_cost, 4),
        "elapsed_seconds": round(elapsed_seconds, 1),
        "product_slug": product_slug,
    }
    _append_usage_log(log_entry, _output_dir() / "usage_log.jsonl")
