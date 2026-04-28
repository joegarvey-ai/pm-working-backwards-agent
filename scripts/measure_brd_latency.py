#!/usr/bin/env python
"""Manual-run latency measurement for the BRD pipeline.

Captures per-task wall-clock timings for the BRD pipeline before and after
landing the compliance-aware workstream so the +10% envelope in
Requirement 14 can be verified.

USAGE

    # Baseline (run on the pre-feature branch before merging):
    uv run python scripts/measure_brd_latency.py --input examples/input.yaml \
        --label baseline --out scripts/brd_latency_baseline.json

    # New topology (run on the feature branch):
    uv run python scripts/measure_brd_latency.py --input examples/input.yaml \
        --label new_topology --out scripts/brd_latency_new.json

    # Compare the two log files manually; the total pipeline wall clock on
    # the new topology must stay within +10% of the baseline mean.

INTERPRETATION

- Per-task timings are absolute seconds from pipeline start.
- Under async execution, the three BRD siblings complete at similar times.
- The +10% envelope check is on the TOTAL pipeline wall clock (elapsed),
  not per-task timings.
- Review pauses are excluded because the script sets skip_validation=True
  and skip_design=True on full_pipeline_crew.

NOTES

- This script calls real LLMs and costs real money. Do not run in CI.
- Use a small, stable reference input so timings are comparable run over
  run. examples/input.yaml is the default.
- Iterations default to 3. Use --iterations to change.
- Only full_pipeline_crew is measured here. The three async BRD siblings
  (structure, cost_risk, compliance) all run inside that crew, so total
  wall clock captures the full BRD envelope. split_brd_crew measurements
  can be added later if needed by running brd_from_prfaq_crew against a
  pre-saved PRFAQ fixture.
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Ensure the repo src/ is on sys.path when running as a plain script.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pm_agent_system.crew import PmAgentSystem  # noqa: E402
from pm_agent_system.input_parser import parse_input  # noqa: E402
from pm_agent_system.main import validate_input  # noqa: E402

load_dotenv()

logger = logging.getLogger(__name__)


def _build_crew_inputs(inputs: dict, target_tool: str = "kiro") -> dict:
    """Build the inputs dict expected by full_pipeline_crew.

    Mirrors the shape assembled in main.cmd_full_pipeline so the crew's
    task templates interpolate without missing-key errors.
    """
    crew_inputs = {k: v for k, v in inputs.items() if k != "publish_destination"}
    crew_inputs.update(
        {
            "prfaq_path": "",
            "research_path": "",
            "design_brief_path": "",
            "visual_style_guide_path": "",
            "requirements_path": "",
            "brd_path": "",
            "target_tool": target_tool,
        }
    )
    return crew_inputs


def _run_iteration(iteration: int, label: str, crew_inputs: dict) -> dict:
    """Run one full_pipeline_crew iteration and return a timing record."""
    task_timings: dict[str, float] = {}
    t0 = time.monotonic()

    def _task_callback(task_output) -> None:
        now = time.monotonic()
        task_name = (
            getattr(task_output, "name", None)
            or type(getattr(task_output, "pydantic", None)).__name__
            or "unknown"
        )
        task_timings[task_name] = now - t0

    crew = PmAgentSystem().full_pipeline_crew(
        skip_validation=True, skip_design=True
    )
    crew.task_callback = _task_callback
    crew.kickoff(inputs=crew_inputs)
    elapsed = time.monotonic() - t0

    return {
        "iteration": iteration,
        "label": label,
        "crew": "full_pipeline_crew",
        "elapsed_seconds": elapsed,
        "task_timings": task_timings,
    }


def _summarize(iterations: list[dict]) -> dict:
    """Compute mean, min, max of elapsed_seconds across iteration records."""
    elapsed = [it["elapsed_seconds"] for it in iterations if "elapsed_seconds" in it]
    if not elapsed:
        return {"count": 0, "mean_seconds": None, "min_seconds": None, "max_seconds": None}
    return {
        "count": len(elapsed),
        "mean_seconds": statistics.fmean(elapsed),
        "min_seconds": min(elapsed),
        "max_seconds": max(elapsed),
    }


def _write_log(out_path: Path, payload: dict) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def _default_out_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("scripts") / f"brd_latency_log_{timestamp}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Measure BRD pipeline wall clock across iterations. "
            "Manual-run only; calls real LLMs."
        )
    )
    parser.add_argument(
        "--input",
        default="examples/input.yaml",
        help="Path to the PM input file (default: examples/input.yaml).",
    )
    parser.add_argument(
        "--label",
        default="run",
        help=(
            "Free-form label recorded with each iteration "
            "(for example: baseline or new_topology)."
        ),
    )
    parser.add_argument(
        "--out",
        default=None,
        help=(
            "Output JSON path for the timing log. "
            "Defaults to scripts/brd_latency_log_{timestamp}.json."
        ),
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Number of iterations to run (default: 3).",
    )

    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}")
        return 2

    out_path = Path(args.out) if args.out else _default_out_path()

    inputs = validate_input(parse_input(str(input_path)))
    crew_inputs = _build_crew_inputs(inputs)

    payload: dict = {
        "label": args.label,
        "input_path": str(input_path),
        "iterations_requested": args.iterations,
        "iterations": [],
        "summary": {},
        "errors": [],
    }

    print(
        f"Running {args.iterations} iteration(s) of full_pipeline_crew "
        f"(label={args.label}) against {input_path}."
    )

    exit_code = 0
    for i in range(1, args.iterations + 1):
        print(f"\n=== Iteration {i} of {args.iterations} ===")
        try:
            record = _run_iteration(i, args.label, crew_inputs)
            payload["iterations"].append(record)
            print(
                f"Iteration {i} finished in {record['elapsed_seconds']:.2f} "
                f"seconds across {len(record['task_timings'])} tasks."
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Iteration %d failed", i)
            payload["errors"].append({"iteration": i, "error": str(exc)})
            print(f"Iteration {i} failed: {exc}")
            exit_code = 1
            break

    payload["summary"] = _summarize(payload["iterations"])
    _write_log(out_path, payload)

    print("\n=== Summary ===")
    print(f"Log written to: {out_path}")
    summary = payload["summary"]
    if summary.get("count"):
        print(
            f"count={summary['count']} "
            f"mean={summary['mean_seconds']:.2f}s "
            f"min={summary['min_seconds']:.2f}s "
            f"max={summary['max_seconds']:.2f}s"
        )
    else:
        print("No successful iterations recorded.")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
