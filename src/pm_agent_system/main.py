#!/usr/bin/env python
"""CLI entry point for the PM Agent System.

Usage:
    # Agent 1 only — research brief
    pm_agent_system research examples/input.yaml

    # Full pipeline — research → PRFAQ generate (Mode 1)
    pm_agent_system generate examples/input.yaml

    # Agent 2 only — revise an existing PRFAQ (Mode 2)
    pm_agent_system revise --prfaq-path output/prfaq_foo_v1.0.md \\
        --context-path notes/legal_feedback.md
    pm_agent_system revise --prfaq-path output/prfaq_foo_v1.0.md \\
        --context-text "Legal wants GDPR language in the CX section"
"""

import argparse
import json
import os
import re
import shutil
import sys
import warnings
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

from pm_agent_system.crew import PmAgentSystem
from pm_agent_system.models import (
    VALID_TARGET_TOOLS,
    BRDOutput,
    CodingPromptOutput,
    PRFAQOutput,
    ResearchOutput,
)
from pm_agent_system.utils import (
    formatted_spec_extension,
    render_brd_to_markdown,
    render_build_spec_to_markdown,
    render_prfaq_to_markdown,
    render_research_to_markdown,
)

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

REQUIRED_FIELDS = ["feature_summary", "goals", "timing", "user_summary"]
ENCOURAGED_FIELDS = ["success_metrics", "known_constraints", "internal_context", "business_context"]
OPTIONAL_FIELDS = ["publish_destination"]


# ---------- Input loading & validation ----------


def load_input(file_path: str) -> dict:
    """Load PM input from a YAML or JSON file."""
    path = Path(file_path)
    if not path.exists():
        print(f"Error: Input file not found: {path}")
        sys.exit(1)

    content = path.read_text(encoding="utf-8")

    if path.suffix in (".yaml", ".yml"):
        return yaml.safe_load(content)
    elif path.suffix == ".json":
        return json.loads(content)
    else:
        print(f"Error: Unsupported file format '{path.suffix}'. Use .yaml, .yml, or .json.")
        sys.exit(1)


def validate_input(inputs: dict) -> dict:
    """Validate required fields and set defaults for encouraged/optional fields."""
    missing = [f for f in REQUIRED_FIELDS if not inputs.get(f, "").strip()]
    if missing:
        print(f"Error: Missing required fields: {', '.join(missing)}")
        print("Please fill in these fields in your input file before running.")
        sys.exit(1)

    for field in ENCOURAGED_FIELDS:
        if not inputs.get(field, "").strip():
            print(f"Note: '{field}' is empty. The agent will proceed without it.")
            inputs[field] = "Not provided."

    for field in OPTIONAL_FIELDS:
        if field not in inputs:
            inputs[field] = ""

    return inputs


def validate_publish_destination(destination: str) -> Path | None:
    """Validate the publish destination path before kickoff."""
    if not destination or not destination.strip():
        return None

    path = Path(destination).expanduser().resolve()

    if not path.exists():
        print(f"\nPublish destination does not exist: {path}")
        response = input("Create it? [y/N]: ").strip().lower()
        if response == "y":
            try:
                path.mkdir(parents=True, exist_ok=True)
                print(f"Created: {path}")
            except Exception as e:
                print(f"Error creating directory: {e}")
                sys.exit(1)
        else:
            print("Aborting. Update publish_destination in your input file or remove it.")
            sys.exit(1)

    if not path.is_dir():
        print(f"Error: publish_destination must be a directory, not a file: {path}")
        sys.exit(1)

    if not os.access(path, os.W_OK):
        print(f"Error: No write permission for: {path}")
        sys.exit(1)

    return path


# ---------- File output helpers ----------


def _slugify(text: str, max_len: int = 50) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in text[:max_len]).strip("_")


def _output_dir() -> Path:
    output_dir = Path(os.getenv("OUTPUT_DIR", "./output"))
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _archive_dir(output_dir: Path) -> Path:
    archive = output_dir / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    return archive


def enforce_retention_policy(output_dir: Path, archive_after_days: int = 30) -> int:
    """Move files in output_dir older than N days into output_dir/archive/.

    Skips the archive subdirectory itself. Returns the number of files moved.
    Silent on individual file errors so this never blocks a real run.
    """
    import time

    if archive_after_days <= 0 or not output_dir.exists():
        return 0

    cutoff = time.time() - (archive_after_days * 86400)
    archive = _archive_dir(output_dir)
    moved = 0
    for entry in output_dir.iterdir():
        if entry.is_dir():
            continue
        try:
            if entry.stat().st_mtime >= cutoff:
                continue
            target = archive / entry.name
            if target.exists():
                stem, suffix = target.stem, target.suffix
                target = archive / f"{stem}_{int(entry.stat().st_mtime)}{suffix}"
            entry.rename(target)
            moved += 1
        except Exception:
            continue
    return moved


def _retention_days() -> int:
    try:
        return int(os.getenv("OUTPUT_RETENTION_DAYS", "30"))
    except ValueError:
        return 30


def save_markdown_brief(markdown: str) -> Path:
    """Write the rendered research brief to OUTPUT_DIR with a timestamped name."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = _output_dir() / f"research_brief_{timestamp}.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def save_prfaq(markdown: str, feature_summary: str, version: str) -> Path:
    """Write a PRFAQ markdown file with the version-aware filename convention."""
    slug = _slugify(feature_summary) or "prfaq"
    path = _output_dir() / f"prfaq_{slug}_v{version}.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def publish_output(source_file: Path, destination_dir: Path, label: str) -> Path:
    """Copy an approved file to the publish destination with a timestamped name."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slugify(label)
    dest_path = destination_dir / f"{timestamp}_{slug}{source_file.suffix}"
    shutil.copy2(source_file, dest_path)
    return dest_path


def save_brd(markdown: str, label: str, version: str) -> Path:
    slug = _slugify(label) or "brd"
    path = _output_dir() / f"brd_{slug}_v{version}.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def save_build_spec(reference_md: str, formatted: str, label: str, target_tool: str) -> tuple[Path, Path]:
    """Write the human-readable wrapper and the tool-ready formatted_spec file.

    Returns (reference_path, formatted_spec_path).
    """
    slug = _slugify(label) or "build_spec"
    out = _output_dir()
    reference_path = out / f"build_spec_{slug}_{target_tool}.md"
    spec_path = out / f"build_spec_{slug}_{target_tool}_formatted{formatted_spec_extension(target_tool)}"
    reference_path.write_text(reference_md, encoding="utf-8")
    spec_path.write_text(formatted, encoding="utf-8")
    return reference_path, spec_path


# ---------- Pydantic extraction ----------


def extract_pydantic_output(crew_result, expected_type):
    """Pull a typed Pydantic instance from a CrewOutput object."""
    if hasattr(crew_result, "pydantic") and isinstance(crew_result.pydantic, expected_type):
        return crew_result.pydantic
    if hasattr(crew_result, "tasks_output") and crew_result.tasks_output:
        for task_output in reversed(crew_result.tasks_output):
            if hasattr(task_output, "pydantic") and isinstance(
                task_output.pydantic, expected_type
            ):
                return task_output.pydantic
    return None


# ---------- Frontmatter helpers ----------

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def read_frontmatter(filepath: Path) -> dict:
    """Parse YAML frontmatter from a markdown file.

    Returns an empty-defaults dict if no frontmatter is found, so older
    files written before frontmatter existed still load cleanly.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception:
        return {"version": "0.0", "slug": "", "type": ""}

    match = FRONTMATTER_RE.match(text)
    if not match:
        return {"version": "0.0", "slug": "", "type": ""}

    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {"version": "0.0", "slug": "", "type": ""}

    data.setdefault("version", "0.0")
    data.setdefault("slug", "")
    data.setdefault("type", "")
    return data


def read_current_version(filepath: Path) -> str:
    """Read version from frontmatter. Defaults to 1.0 if not found."""
    fm = read_frontmatter(filepath)
    v = str(fm.get("version", "0.0"))
    return v if v != "0.0" else "1.0"


def bump_version(version: str) -> str:
    major, minor = version.split(".")
    return f"{major}.{int(minor) + 1}"


# ---------- Subcommand: research ----------


def cmd_research(args: argparse.Namespace) -> None:
    """Run Agent 1 only and produce a research brief."""
    inputs = validate_input(load_input(args.input_file))

    publish_dir = validate_publish_destination(inputs.get("publish_destination", ""))
    if publish_dir:
        print(f"Approved briefs will publish to: {publish_dir}")

    print(f"\nStarting research for: {inputs['feature_summary'][:80]}...")
    print("The agent will pause for your review before finalizing.\n")

    crew_inputs = {k: v for k, v in inputs.items() if k != "publish_destination"}

    skip = getattr(args, "skip_validation", False)
    try:
        result = PmAgentSystem().research_crew(skip_validation=skip).kickoff(inputs=crew_inputs)
    except Exception as e:
        print(f"\nError running crew: {e}")
        sys.exit(1)

    research = extract_pydantic_output(result, ResearchOutput)
    if research is None:
        print("\nError: Agent did not return a valid ResearchOutput object.")
        print("Raw output:", result)
        sys.exit(1)

    markdown = render_research_to_markdown(research)
    working_copy = save_markdown_brief(markdown)
    print(f"\nResearch complete. Working copy saved to: {working_copy}")

    if publish_dir:
        try:
            published = publish_output(working_copy, publish_dir, inputs["feature_summary"])
            print(f"Published approved brief to: {published}")
        except Exception as e:
            print(f"Warning: Failed to publish to {publish_dir}: {e}")


# ---------- Subcommand: generate (Mode 1) ----------


def cmd_generate(args: argparse.Namespace) -> None:
    """Run the full pipeline: Agent 1 research → Agent 2 PRFAQ generate."""
    inputs = validate_input(load_input(args.input_file))

    publish_dir = validate_publish_destination(inputs.get("publish_destination", ""))
    if publish_dir:
        print(f"Approved PRFAQs will publish to: {publish_dir}")

    print(f"\nStarting research + PRFAQ generation for: {inputs['feature_summary'][:80]}...")
    print("The agent will pause for review after research and again after the PRFAQ.\n")

    crew_inputs = {k: v for k, v in inputs.items() if k != "publish_destination"}

    skip = getattr(args, "skip_validation", False)
    try:
        result = PmAgentSystem().research_and_generate_crew(skip_validation=skip).kickoff(inputs=crew_inputs)
    except Exception as e:
        print(f"\nError running crew: {e}")
        sys.exit(1)

    prfaq = extract_pydantic_output(result, PRFAQOutput)
    if prfaq is None:
        print("\nError: Agent 2 did not return a valid PRFAQOutput object.")
        print("Raw output:", result)
        sys.exit(1)

    initial_version = prfaq.version_history[-1].version if prfaq.version_history else "1.0"
    slug = _slugify(inputs["feature_summary"])
    markdown = render_prfaq_to_markdown(prfaq, slug=slug)
    working_copy = save_prfaq(markdown, inputs["feature_summary"], initial_version)
    print(f"\nPRFAQ complete. Working copy saved to: {working_copy}")

    if publish_dir:
        try:
            published = publish_output(working_copy, publish_dir, inputs["feature_summary"])
            print(f"Published approved PRFAQ to: {published}")
        except Exception as e:
            print(f"Warning: Failed to publish to {publish_dir}: {e}")


# ---------- Subcommand: revise (Mode 2) ----------


def cmd_revise(args: argparse.Namespace) -> None:
    """Run Agent 2 only against an existing PRFAQ with revision context."""
    if not args.context_path and not args.context_text:
        print("Error: --revise requires at least one of --context-path or --context-text.")
        sys.exit(1)

    prfaq_path = Path(args.prfaq_path).expanduser().resolve()
    if not prfaq_path.exists() or not prfaq_path.is_file():
        print(f"Error: PRFAQ file not found: {prfaq_path}")
        sys.exit(1)

    current_version = read_current_version(prfaq_path)
    next_version = bump_version(current_version)

    context_path_str = ""
    if args.context_path:
        cp = Path(args.context_path).expanduser().resolve()
        if not cp.exists():
            print(f"Error: Context path not found: {cp}")
            sys.exit(1)
        context_path_str = str(cp)

    crew_inputs = {
        "prfaq_path": str(prfaq_path),
        "context_path": context_path_str,
        "context_text": args.context_text or "",
    }

    print(f"\nRevising {prfaq_path.name} (v{current_version} → v{next_version})")
    print("The agent will pause to confirm which sections to revise.\n")

    try:
        result = PmAgentSystem().revise_prfaq_crew().kickoff(inputs=crew_inputs)
    except Exception as e:
        print(f"\nError running crew: {e}")
        sys.exit(1)

    prfaq = extract_pydantic_output(result, PRFAQOutput)
    if prfaq is None:
        print("\nError: Agent 2 did not return a valid PRFAQOutput object.")
        print("Raw output:", result)
        sys.exit(1)

    output_version = prfaq.version_history[-1].version if prfaq.version_history else next_version

    # Reuse the original slug from frontmatter when available so revisions stay grouped.
    fm = read_frontmatter(prfaq_path)
    label = fm.get("slug") or re.sub(r"_v\d+\.\d+$", "", prfaq_path.stem.replace("prfaq_", ""))
    markdown = render_prfaq_to_markdown(prfaq, slug=label)
    working_copy = save_prfaq(markdown, label, output_version)
    print(f"\nRevision complete. Working copy saved to: {working_copy}")


# ---------- Subcommand: full-pipeline (Agents 1 → 2 → 3) ----------


def cmd_full_pipeline(args: argparse.Namespace) -> None:
    inputs = validate_input(load_input(args.input_file))
    publish_dir = validate_publish_destination(inputs.get("publish_destination", ""))

    target_tool = (args.target_tool or os.getenv("DEFAULT_TARGET_TOOL", "kiro")).strip()
    if target_tool not in VALID_TARGET_TOOLS:
        print(f"Error: --target-tool must be one of {VALID_TARGET_TOOLS}")
        sys.exit(1)

    crew_inputs = {k: v for k, v in inputs.items() if k != "publish_destination"}
    # Empty path placeholders so the BRD/build-spec tasks don't break templating.
    crew_inputs.update({
        "prfaq_path": "",
        "research_path": "",
        "brd_path": "",
        "target_tool": target_tool,
    })

    print(f"\nFull pipeline starting for: {inputs['feature_summary'][:80]}...")
    print(f"Target tool for build spec: {target_tool}")
    print("Human review checkpoints will pause after each agent.\n")

    skip = getattr(args, "skip_validation", False)
    try:
        result = PmAgentSystem().full_pipeline_crew(skip_validation=skip).kickoff(inputs=crew_inputs)
    except Exception as e:
        print(f"\nError running crew: {e}")
        sys.exit(1)

    spec = extract_pydantic_output(result, CodingPromptOutput)
    if spec is None:
        print("\nError: pipeline did not return a valid CodingPromptOutput object.")
        print("Raw output:", result)
        sys.exit(1)

    # Save BRD if it's available in tasks_output
    label = inputs["feature_summary"]
    slug = _slugify(label)
    if hasattr(result, "tasks_output"):
        for task_output in result.tasks_output:
            if hasattr(task_output, "pydantic") and isinstance(task_output.pydantic, BRDOutput):
                brd_version = (
                    task_output.pydantic.version_history[-1].version
                    if task_output.pydantic.version_history else "1.0"
                )
                brd_md = render_brd_to_markdown(task_output.pydantic, slug=slug)
                brd_path = save_brd(brd_md, label, brd_version)
                print(f"BRD saved to: {brd_path}")

    reference_md = render_build_spec_to_markdown(spec, slug=slug)
    ref_path, spec_path = save_build_spec(reference_md, spec.formatted_spec, label, target_tool)
    print(f"Build spec reference saved to: {ref_path}")
    print(f"Tool-ready formatted spec saved to: {spec_path}")

    if publish_dir:
        try:
            publish_output(spec_path, publish_dir, f"{label}_{target_tool}")
            print(f"Published formatted spec to: {publish_dir}")
        except Exception as e:
            print(f"Warning: publish failed: {e}")


# ---------- Subcommand: brd (Agent 3, BRD + build spec from approved PRFAQ) ----------


def cmd_brd(args: argparse.Namespace) -> None:
    inputs = validate_input(load_input(args.input_file))
    prfaq_path = Path(args.prfaq_path).expanduser().resolve()
    if not prfaq_path.exists():
        print(f"Error: PRFAQ file not found: {prfaq_path}")
        sys.exit(1)

    research_path_arg = ""
    if args.research_path:
        rp = Path(args.research_path).expanduser().resolve()
        if not rp.exists():
            print(f"Error: Research file not found: {rp}")
            sys.exit(1)
        research_path_arg = str(rp)

    target_tool = (args.target_tool or os.getenv("DEFAULT_TARGET_TOOL", "kiro")).strip()
    if target_tool not in VALID_TARGET_TOOLS:
        print(f"Error: --target-tool must be one of {VALID_TARGET_TOOLS}")
        sys.exit(1)

    crew_inputs = {k: v for k, v in inputs.items() if k != "publish_destination"}
    crew_inputs.update({
        "prfaq_path": str(prfaq_path),
        "research_path": research_path_arg,
        "brd_path": "",
        "target_tool": target_tool,
    })

    print(f"\nGenerating BRD + build spec from PRFAQ: {prfaq_path.name}")
    print(f"Target tool: {target_tool}\n")

    try:
        result = PmAgentSystem().brd_from_prfaq_crew().kickoff(inputs=crew_inputs)
    except Exception as e:
        print(f"\nError running crew: {e}")
        sys.exit(1)

    label = inputs["feature_summary"]
    slug = _slugify(label)
    if hasattr(result, "tasks_output"):
        for task_output in result.tasks_output:
            if hasattr(task_output, "pydantic") and isinstance(task_output.pydantic, BRDOutput):
                brd_version = (
                    task_output.pydantic.version_history[-1].version
                    if task_output.pydantic.version_history else "1.0"
                )
                brd_md = render_brd_to_markdown(task_output.pydantic, slug=slug)
                brd_path = save_brd(brd_md, label, brd_version)
                print(f"BRD saved to: {brd_path}")

    spec = extract_pydantic_output(result, CodingPromptOutput)
    if spec is None:
        print("\nError: did not return a valid CodingPromptOutput.")
        sys.exit(1)
    reference_md = render_build_spec_to_markdown(spec, slug=slug)
    ref_path, spec_path = save_build_spec(reference_md, spec.formatted_spec, label, target_tool)
    print(f"Build spec reference: {ref_path}")
    print(f"Formatted spec:       {spec_path}")


# ---------- Subcommand: build-spec (Agent 3 Mode 3) ----------


def cmd_build_spec(args: argparse.Namespace) -> None:
    brd_path = Path(args.brd_path).expanduser().resolve()
    if not brd_path.exists():
        print(f"Error: BRD file not found: {brd_path}")
        sys.exit(1)

    target_tool = (args.target_tool or os.getenv("DEFAULT_TARGET_TOOL", "kiro")).strip()
    if target_tool not in VALID_TARGET_TOOLS:
        print(f"Error: --target-tool must be one of {VALID_TARGET_TOOLS}")
        sys.exit(1)

    crew_inputs = {
        "brd_path": str(brd_path),
        "target_tool": target_tool,
        # generate_brd placeholders unused here, but supply in case templating walks them
        "prfaq_path": "",
        "research_path": "",
    }

    print(f"\nRegenerating build spec from {brd_path.name} for target tool: {target_tool}\n")

    try:
        result = PmAgentSystem().regenerate_build_spec_crew().kickoff(inputs=crew_inputs)
    except Exception as e:
        print(f"\nError running crew: {e}")
        sys.exit(1)

    spec = extract_pydantic_output(result, CodingPromptOutput)
    if spec is None:
        print("\nError: did not return a valid CodingPromptOutput.")
        sys.exit(1)

    fm = read_frontmatter(brd_path)
    label = fm.get("slug") or re.sub(r"_v\d+\.\d+$", "", brd_path.stem.replace("brd_", ""))
    reference_md = render_build_spec_to_markdown(spec, slug=label)
    ref_path, spec_path = save_build_spec(reference_md, spec.formatted_spec, label, target_tool)
    print(f"Build spec reference: {ref_path}")
    print(f"Formatted spec:       {spec_path}")


# ---------- Subcommand: revise-brd (Agent 3 Mode 2) ----------


def cmd_revise_brd(args: argparse.Namespace) -> None:
    if not args.context_path and not args.context_text:
        print("Error: revise-brd requires at least one of --context-path or --context-text.")
        sys.exit(1)

    brd_path = Path(args.brd_path).expanduser().resolve()
    if not brd_path.exists():
        print(f"Error: BRD file not found: {brd_path}")
        sys.exit(1)

    current_version = read_current_version(brd_path)
    next_version = bump_version(current_version)

    context_path_str = ""
    if args.context_path:
        cp = Path(args.context_path).expanduser().resolve()
        if not cp.exists():
            print(f"Error: Context path not found: {cp}")
            sys.exit(1)
        context_path_str = str(cp)

    crew_inputs = {
        "brd_path": str(brd_path),
        "context_path": context_path_str,
        "context_text": args.context_text or "",
    }

    print(f"\nRevising {brd_path.name} (v{current_version} → v{next_version})\n")

    try:
        result = PmAgentSystem().revise_brd_crew().kickoff(inputs=crew_inputs)
    except Exception as e:
        print(f"\nError running crew: {e}")
        sys.exit(1)

    brd = extract_pydantic_output(result, BRDOutput)
    if brd is None:
        print("\nError: Agent 3 did not return a valid BRDOutput.")
        sys.exit(1)

    output_version = brd.version_history[-1].version if brd.version_history else next_version
    fm = read_frontmatter(brd_path)
    label = fm.get("slug") or re.sub(r"_v\d+\.\d+$", "", brd_path.stem.replace("brd_", ""))
    markdown = render_brd_to_markdown(brd, slug=label)
    working_copy = save_brd(markdown, label, output_version)
    print(f"\nRevision complete. Working copy saved to: {working_copy}")


# ---------- Argparse wiring ----------


def cmd_clean(args: argparse.Namespace) -> None:
    """Manage output retention: list, archive old files, or delete archive."""
    output_dir = _output_dir()
    archive = _archive_dir(output_dir)

    if args.list:
        live = sorted(p.name for p in output_dir.iterdir() if p.is_file())
        archived = sorted(p.name for p in archive.iterdir() if p.is_file())
        print(f"Live files in {output_dir} ({len(live)}):")
        for n in live:
            print(f"  {n}")
        print(f"\nArchived files in {archive} ({len(archived)}):")
        for n in archived:
            print(f"  {n}")
        return

    if args.delete_archive:
        files = [p for p in archive.iterdir() if p.is_file()]
        if not files:
            print(f"Archive is already empty: {archive}")
            return
        confirm = input(
            f"Permanently delete {len(files)} files from {archive}? [y/N] "
        ).strip().lower()
        if confirm != "y":
            print("Aborted.")
            return
        for p in files:
            try:
                p.unlink()
            except Exception as e:
                print(f"  failed to delete {p.name}: {e}")
        print(f"Deleted {len(files)} files from archive.")
        return

    if args.archive:
        days = _retention_days()
        moved = enforce_retention_policy(output_dir, archive_after_days=days)
        print(f"Archived {moved} files older than {days} days to {archive}.")
        return

    print("Nothing to do. Use --list, --archive, or --delete-archive.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pm_agent_system")
    sub = parser.add_subparsers(dest="command", required=True)

    p_research = sub.add_parser("research", help="Run Agent 1 only (research brief)")
    p_research.add_argument("input_file", help="Path to YAML or JSON input file")
    p_research.add_argument("--skip-validation", action="store_true", help="Skip the pre-research challenge questions")
    p_research.set_defaults(func=cmd_research)

    p_generate = sub.add_parser(
        "generate", help="Run Agent 1 then Agent 2 to produce a PRFAQ v1.0"
    )
    p_generate.add_argument("input_file", help="Path to YAML or JSON input file")
    p_generate.add_argument("--skip-validation", action="store_true", help="Skip the pre-research challenge questions")
    p_generate.set_defaults(func=cmd_generate)

    p_revise = sub.add_parser("revise", help="Run Agent 2 only to revise an existing PRFAQ")
    p_revise.add_argument("--prfaq-path", required=True, help="Path to current PRFAQ markdown")
    p_revise.add_argument(
        "--context-path", help="File or folder containing revision context"
    )
    p_revise.add_argument(
        "--context-text", help="Inline revision instructions"
    )
    p_revise.set_defaults(func=cmd_revise)

    # ----- Agent 3 commands -----

    p_full = sub.add_parser(
        "full-pipeline",
        help="Run all three agents end-to-end (research → PRFAQ → BRD → build spec)",
    )
    p_full.add_argument("input_file", help="Path to YAML or JSON input file")
    p_full.add_argument("--skip-validation", action="store_true", help="Skip the pre-research challenge questions")
    p_full.add_argument(
        "--target-tool",
        choices=VALID_TARGET_TOOLS,
        help="Target coding tool for the build spec (defaults to DEFAULT_TARGET_TOOL or kiro)",
    )
    p_full.set_defaults(func=cmd_full_pipeline)

    p_brd = sub.add_parser(
        "brd",
        help="Run Agent 3 only — generate BRD + build spec from an approved PRFAQ",
    )
    p_brd.add_argument("input_file", help="Path to original YAML/JSON input (for context)")
    p_brd.add_argument("--prfaq-path", required=True, help="Path to approved PRFAQ markdown")
    p_brd.add_argument("--research-path", help="Optional path to research brief markdown")
    p_brd.add_argument("--target-tool", choices=VALID_TARGET_TOOLS)
    p_brd.set_defaults(func=cmd_brd)

    p_spec = sub.add_parser(
        "build-spec",
        help="Run Agent 3 only — regenerate build spec from an approved BRD",
    )
    p_spec.add_argument("--brd-path", required=True, help="Path to approved BRD markdown")
    p_spec.add_argument("--target-tool", choices=VALID_TARGET_TOOLS)
    p_spec.set_defaults(func=cmd_build_spec)

    p_rbrd = sub.add_parser(
        "revise-brd",
        help="Run Agent 3 only — revise an existing BRD",
    )
    p_rbrd.add_argument("--brd-path", required=True, help="Path to current BRD markdown")
    p_rbrd.add_argument("--context-path", help="File or folder with revision context")
    p_rbrd.add_argument("--context-text", help="Inline revision instructions")
    p_rbrd.set_defaults(func=cmd_revise_brd)

    p_clean = sub.add_parser("clean", help="Manage output retention (archive/list/delete)")
    p_clean.add_argument("--archive", action="store_true", help="Archive files older than retention window")
    p_clean.add_argument("--delete-archive", action="store_true", help="Permanently delete archived files (with confirmation)")
    p_clean.add_argument("--list", action="store_true", help="List live and archived output files")
    p_clean.set_defaults(func=cmd_clean)

    return parser


def run():
    """CLI entry point."""
    load_dotenv()
    parser = _build_parser()
    args = parser.parse_args()
    if args.command != "clean":
        enforce_retention_policy(_output_dir(), archive_after_days=_retention_days())
    args.func(args)


# ---------- crewai train/replay/test entry points ----------


def train():
    """Train the crew for a given number of iterations."""
    load_dotenv()
    inputs = _load_default_inputs()
    try:
        PmAgentSystem().crew().train(
            n_iterations=int(sys.argv[1]), filename=sys.argv[2], inputs=inputs
        )
    except Exception as e:
        raise Exception(f"An error occurred while training the crew: {e}")


def replay():
    """Replay the crew execution from a specific task."""
    try:
        PmAgentSystem().crew().replay(task_id=sys.argv[1])
    except Exception as e:
        raise Exception(f"An error occurred while replaying the crew: {e}")


def test():
    """Test the crew execution and returns the results."""
    load_dotenv()
    inputs = _load_default_inputs()
    try:
        PmAgentSystem().crew().test(
            n_iterations=int(sys.argv[1]), eval_llm=sys.argv[2], inputs=inputs
        )
    except Exception as e:
        raise Exception(f"An error occurred while testing the crew: {e}")


def _load_default_inputs() -> dict:
    """Load the example input file for train/test commands."""
    example_path = Path(__file__).parent.parent.parent / "input" / "example_input.yaml"
    if example_path.exists():
        data = yaml.safe_load(example_path.read_text())
        data.pop("publish_destination", None)
        return data
    return {
        "feature_summary": "Test feature",
        "goals": "Test goals",
        "timing": "Q3 2026",
        "user_summary": "Test users",
        "success_metrics": "Not provided.",
        "known_constraints": "Not provided.",
        "internal_context": "Not provided.",
        "business_context": "Not provided.",
    }
