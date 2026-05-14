"""Trace export: standalone HTML timeline viewer for RunRecords.

Generates a self-contained HTML file with a flamegraph-style timeline
showing LLM calls, tool calls, cost breakdown, and agent swimlanes.
No external dependencies or hosting required.

Usage:
    uv run python -m pm_agent_system.trace_export tests/recordings/prfaq_baseline.json

    # Or programmatically:
    from pm_agent_system.trace_export import export_html
    export_html("tests/recordings/prfaq_baseline.json", "trace.html")
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

from tests.harness import load_record
from tests.harness.models import RunRecord


def _build_timeline_data(record: RunRecord) -> list[dict]:
    """Build timeline entries from LLM and tool call records."""
    entries = []
    base_time = record.llm_calls[0].timestamp if record.llm_calls else 0

    for call in record.llm_calls:
        entries.append({
            "type": "llm",
            "agent": call.agent_name.strip(),
            "task": call.task_name.strip(),
            "start": call.timestamp - base_time,
            "duration": call.duration_s,
            "cost": call.estimated_cost_usd,
            "model": call.model_id,
            "tokens_in": call.input_tokens,
            "tokens_out": call.output_tokens,
            "is_tool_use": call.output_text.startswith("[{") or call.output_text.startswith("__pydantic__:"),
        })

    for call in record.tool_calls:
        entries.append({
            "type": "tool",
            "agent": "",
            "task": "",
            "tool_name": call.tool_name,
            "start": call.timestamp - base_time,
            "duration": call.duration_s,
            "error": call.error_class,
        })

    entries.sort(key=lambda e: e["start"])
    return entries


def _generate_html(record: RunRecord) -> str:
    """Generate a self-contained HTML trace viewer."""
    entries = _build_timeline_data(record)
    total_duration = record.latency_summary.total_s
    total_cost = record.cost_summary.total_usd

    agents = sorted(set(e["agent"] for e in entries if e.get("agent")))
    agent_colors = {}
    palette = ["#4A90D9", "#D94A4A", "#4AD99B", "#D9A54A", "#9B4AD9", "#4AD9D9", "#D94A9B", "#7AD94A"]
    for i, agent in enumerate(agents):
        agent_colors[agent] = palette[i % len(palette)]

    entries_json = json.dumps(entries)
    agent_colors_json = json.dumps(agent_colors)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Pipeline Trace: {record.run_id[:8]}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #1a1a2e; color: #eee; padding: 20px; }}
h1 {{ font-size: 18px; margin-bottom: 8px; color: #fff; }}
.summary {{ display: flex; gap: 24px; margin-bottom: 20px; padding: 12px; background: #16213e; border-radius: 6px; }}
.summary .stat {{ text-align: center; }}
.summary .stat .value {{ font-size: 22px; font-weight: 700; color: #4AD9D9; }}
.summary .stat .label {{ font-size: 11px; color: #888; text-transform: uppercase; }}
.timeline {{ position: relative; background: #0f3460; border-radius: 6px; padding: 16px; margin-bottom: 20px; overflow-x: auto; }}
.swimlane {{ margin-bottom: 12px; position: relative; min-height: 32px; }}
.swimlane-label {{ font-size: 11px; color: #aaa; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 300px; }}
.bar-container {{ position: relative; height: 24px; background: #1a1a2e; border-radius: 3px; }}
.bar {{ position: absolute; height: 24px; border-radius: 3px; cursor: pointer; opacity: 0.85; transition: opacity 0.15s; display: flex; align-items: center; padding: 0 4px; font-size: 10px; color: #fff; overflow: hidden; white-space: nowrap; }}
.bar:hover {{ opacity: 1; z-index: 10; }}
.bar.tool {{ background: #555; opacity: 0.6; height: 16px; top: 4px; }}
.bar.llm {{ }}
.tooltip {{ display: none; position: fixed; background: #222; border: 1px solid #444; border-radius: 4px; padding: 8px 12px; font-size: 12px; z-index: 100; max-width: 400px; pointer-events: none; }}
.tooltip.visible {{ display: block; }}
.legend {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }}
.legend-item {{ display: flex; align-items: center; gap: 6px; font-size: 12px; }}
.legend-swatch {{ width: 14px; height: 14px; border-radius: 3px; }}
.cost-breakdown {{ background: #16213e; border-radius: 6px; padding: 16px; }}
.cost-breakdown h2 {{ font-size: 14px; margin-bottom: 8px; }}
.cost-row {{ display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid #1a1a2e; font-size: 13px; }}
.cost-row .name {{ color: #ccc; }}
.cost-row .amount {{ color: #4AD9D9; font-weight: 600; }}
</style>
</head>
<body>
<h1>Pipeline Trace: {record.run_id[:8]}</h1>
<div class="summary">
  <div class="stat"><div class="value">{total_duration:.0f}s</div><div class="label">Duration</div></div>
  <div class="stat"><div class="value">${total_cost:.4f}</div><div class="label">Cost</div></div>
  <div class="stat"><div class="value">{len(record.llm_calls)}</div><div class="label">LLM Calls</div></div>
  <div class="stat"><div class="value">{len(record.tool_calls)}</div><div class="label">Tool Calls</div></div>
  <div class="stat"><div class="value">{len(record.prompt_snapshots)}</div><div class="label">Snapshots</div></div>
</div>

<div class="legend" id="legend"></div>
<div class="timeline" id="timeline"></div>

<div class="cost-breakdown">
  <h2>Cost by Agent</h2>
  <div id="cost-rows"></div>
</div>

<div class="tooltip" id="tooltip"></div>

<script>
const entries = {entries_json};
const agentColors = {agent_colors_json};
const totalDuration = {total_duration};
const perAgentCost = {json.dumps(record.cost_summary.per_agent)};

// Build legend
const legendEl = document.getElementById('legend');
Object.entries(agentColors).forEach(([name, color]) => {{
  const item = document.createElement('div');
  item.className = 'legend-item';
  item.innerHTML = `<div class="legend-swatch" style="background:${{color}}"></div>${{name}}`;
  legendEl.appendChild(item);
}});

// Build swimlanes (group by agent)
const timelineEl = document.getElementById('timeline');
const agents = [...new Set(entries.filter(e => e.agent).map(e => e.agent))];

agents.forEach(agent => {{
  const lane = document.createElement('div');
  lane.className = 'swimlane';

  const label = document.createElement('div');
  label.className = 'swimlane-label';
  label.textContent = agent;
  lane.appendChild(label);

  const container = document.createElement('div');
  container.className = 'bar-container';

  const agentEntries = entries.filter(e => e.agent === agent);
  agentEntries.forEach(entry => {{
    const bar = document.createElement('div');
    const left = (entry.start / totalDuration) * 100;
    const width = Math.max((entry.duration / totalDuration) * 100, 0.3);
    bar.className = `bar ${{entry.type}}`;
    bar.style.left = `${{left}}%`;
    bar.style.width = `${{width}}%`;
    bar.style.background = agentColors[agent] || '#666';
    if (entry.type === 'tool') bar.style.background = '#555';

    const labelText = entry.type === 'llm'
      ? (entry.is_tool_use ? 'tool-use' : `${{entry.tokens_out}}tok`)
      : entry.tool_name;
    bar.textContent = width > 3 ? labelText : '';

    bar.addEventListener('mouseenter', (ev) => {{
      const tip = document.getElementById('tooltip');
      let html = `<strong>${{entry.type.toUpperCase()}}</strong><br>`;
      if (entry.type === 'llm') {{
        html += `Model: ${{entry.model}}<br>`;
        html += `Tokens: ${{entry.tokens_in}} in / ${{entry.tokens_out}} out<br>`;
        html += `Cost: $${{entry.cost.toFixed(4)}}<br>`;
        html += `Duration: ${{entry.duration.toFixed(1)}}s<br>`;
        html += `Task: ${{entry.task}}`;
      }} else {{
        html += `Tool: ${{entry.tool_name}}<br>`;
        html += `Duration: ${{entry.duration.toFixed(1)}}s`;
        if (entry.error) html += `<br>Error: ${{entry.error}}`;
      }}
      tip.innerHTML = html;
      tip.style.left = (ev.clientX + 12) + 'px';
      tip.style.top = (ev.clientY + 12) + 'px';
      tip.classList.add('visible');
    }});
    bar.addEventListener('mouseleave', () => {{
      document.getElementById('tooltip').classList.remove('visible');
    }});

    container.appendChild(bar);
  }});

  lane.appendChild(container);
  timelineEl.appendChild(lane);
}});

// Tool calls lane
const toolEntries = entries.filter(e => e.type === 'tool');
if (toolEntries.length) {{
  const lane = document.createElement('div');
  lane.className = 'swimlane';
  const label = document.createElement('div');
  label.className = 'swimlane-label';
  label.textContent = 'Tool Calls';
  lane.appendChild(label);
  const container = document.createElement('div');
  container.className = 'bar-container';
  toolEntries.forEach(entry => {{
    const bar = document.createElement('div');
    const left = (entry.start / totalDuration) * 100;
    const width = Math.max((entry.duration / totalDuration) * 100, 0.3);
    bar.className = 'bar tool';
    bar.style.left = `${{left}}%`;
    bar.style.width = `${{width}}%`;
    bar.textContent = width > 2 ? entry.tool_name : '';
    bar.addEventListener('mouseenter', (ev) => {{
      const tip = document.getElementById('tooltip');
      tip.innerHTML = `<strong>TOOL</strong><br>Tool: ${{entry.tool_name}}<br>Duration: ${{entry.duration.toFixed(1)}}s${{entry.error ? '<br>Error: ' + entry.error : ''}}`;
      tip.style.left = (ev.clientX + 12) + 'px';
      tip.style.top = (ev.clientY + 12) + 'px';
      tip.classList.add('visible');
    }});
    bar.addEventListener('mouseleave', () => document.getElementById('tooltip').classList.remove('visible'));
    container.appendChild(bar);
  }});
  lane.appendChild(container);
  timelineEl.appendChild(lane);
}}

// Cost breakdown
const costEl = document.getElementById('cost-rows');
Object.entries(perAgentCost).sort((a, b) => b[1] - a[1]).forEach(([name, cost]) => {{
  const row = document.createElement('div');
  row.className = 'cost-row';
  row.innerHTML = `<span class="name">${{name.trim()}}</span><span class="amount">$${{cost.toFixed(4)}}</span>`;
  costEl.appendChild(row);
}});
</script>
</body>
</html>"""


def export_html(recording_path: str, output_path: str | None = None) -> str:
    """Export a RunRecord as a standalone HTML trace viewer.

    Args:
        recording_path: Path to a RunRecord JSON file.
        output_path: Where to write the HTML. Defaults to recording_path with .html extension.

    Returns:
        The output path.
    """
    record = load_record(recording_path)
    html_content = _generate_html(record)

    if output_path is None:
        output_path = str(Path(recording_path).with_suffix(".html"))

    Path(output_path).write_text(html_content, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export RunRecord as HTML trace viewer")
    parser.add_argument("recording", help="Path to RunRecord JSON file")
    parser.add_argument("-o", "--output", help="Output HTML path (default: same name with .html)")
    args = parser.parse_args()

    output = export_html(args.recording, args.output)
    print(f"Trace exported to: {output}")


if __name__ == "__main__":
    main()
