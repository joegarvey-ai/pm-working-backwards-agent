"""Run record aggregation and trend reporting.

CLI command: uv run python -m pm_agent_system.harness_trends --since 7d

Aggregates cost, latency, and eval scores across all RunRecords in
the recordings directory. Emits a markdown summary.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests.harness import load_record
from tests.harness.models import RunRecord


def _parse_since(since_str: str) -> datetime:
    """Parse a relative duration like '7d', '24h', '30d' into an absolute cutoff."""
    unit = since_str[-1].lower()
    amount = int(since_str[:-1])
    now = datetime.now(timezone.utc)
    if unit == "d":
        return now - timedelta(days=amount)
    if unit == "h":
        return now - timedelta(hours=amount)
    raise ValueError(f"Unsupported duration unit: {unit}. Use 'd' (days) or 'h' (hours).")


def _find_recordings(directory: Path, since: datetime) -> list[RunRecord]:
    """Load all RunRecord JSON files modified after the cutoff."""
    records: list[RunRecord] = []
    for json_file in sorted(directory.glob("*.json")):
        try:
            record = load_record(str(json_file))
            record_time = datetime.fromisoformat(record.created_at)
            if record_time >= since:
                records.append(record)
        except Exception:
            continue
    return records


def generate_trends_report(records: list[RunRecord]) -> str:
    """Generate a markdown summary of trends across runs."""
    if not records:
        return "No recordings found in the specified time range.\n"

    lines: list[str] = []
    lines.append("# Harness Trends Report")
    lines.append(f"\nRuns analyzed: {len(records)}")
    lines.append(f"Date range: {records[0].created_at[:10]} to {records[-1].created_at[:10]}")

    # Cost summary
    costs = [r.cost_summary.total_usd for r in records]
    lines.append("\n## Cost")
    lines.append(f"- Average: ${sum(costs) / len(costs):.4f}")
    lines.append(f"- Min: ${min(costs):.4f}")
    lines.append(f"- Max: ${max(costs):.4f}")
    lines.append(f"- Total across all runs: ${sum(costs):.4f}")

    # Latency summary
    latencies = [r.latency_summary.total_s for r in records]
    lines.append("\n## Latency")
    lines.append(f"- Average: {sum(latencies) / len(latencies):.1f}s")
    lines.append(f"- Min: {min(latencies):.1f}s")
    lines.append(f"- Max: {max(latencies):.1f}s")
    sorted_latencies = sorted(latencies)
    p50_idx = len(sorted_latencies) // 2
    p95_idx = min(int(len(sorted_latencies) * 0.95), len(sorted_latencies) - 1)
    lines.append(f"- p50: {sorted_latencies[p50_idx]:.1f}s")
    lines.append(f"- p95: {sorted_latencies[p95_idx]:.1f}s")

    # LLM call volume
    llm_counts = [len(r.llm_calls) for r in records]
    tool_counts = [len(r.tool_calls) for r in records]
    lines.append("\n## Call Volume")
    lines.append(f"- Avg LLM calls per run: {sum(llm_counts) / len(llm_counts):.1f}")
    lines.append(f"- Avg tool calls per run: {sum(tool_counts) / len(tool_counts):.1f}")

    # Per-agent cost breakdown
    agent_costs: dict[str, list[float]] = {}
    for r in records:
        for agent_name, cost in r.cost_summary.per_agent.items():
            agent_costs.setdefault(agent_name.strip(), []).append(cost)

    if agent_costs:
        lines.append("\n## Per-Agent Cost (average)")
        for agent_name in sorted(agent_costs.keys()):
            costs_list = agent_costs[agent_name]
            avg = sum(costs_list) / len(costs_list)
            lines.append(f"- {agent_name}: ${avg:.4f}")

    # Prompt snapshot drift (if multiple runs have snapshots)
    runs_with_snapshots = [r for r in records if r.prompt_snapshots]
    if len(runs_with_snapshots) >= 2:
        from tests.harness.models import PromptSnapshot

        first = runs_with_snapshots[0]
        last = runs_with_snapshots[-1]
        diffs_found = 0
        for s1, s2 in zip(first.prompt_snapshots, last.prompt_snapshots):
            diff = PromptSnapshot.diff(s1, s2)
            if diff:
                diffs_found += 1

        lines.append("\n## Prompt Drift")
        if diffs_found == 0:
            lines.append("- No prompt drift detected between first and last run.")
        else:
            lines.append(f"- {diffs_found} prompt(s) changed between first and last run.")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Harness trend reporting")
    parser.add_argument(
        "--since",
        default="7d",
        help="Time window (e.g., '7d', '24h', '30d'). Default: 7d",
    )
    parser.add_argument(
        "--dir",
        default="tests/recordings",
        help="Directory containing RunRecord JSON files. Default: tests/recordings",
    )
    args = parser.parse_args()

    since = _parse_since(args.since)
    recordings_dir = Path(args.dir)

    if not recordings_dir.exists():
        print(f"Error: directory '{recordings_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)

    records = _find_recordings(recordings_dir, since)
    report = generate_trends_report(records)
    print(report)


if __name__ == "__main__":
    main()
