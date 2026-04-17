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
import logging
import os
import re
import shutil
import sys
import warnings
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

from pm_agent_system.checkpoint import (
    completed_stages,
    compute_input_hash,
    delete_checkpoint,
    load_checkpoint,
    new_checkpoint,
    record_artifact,
    save_checkpoint,
)
from pm_agent_system.crew import PmAgentSystem, _MODEL
from pm_agent_system.html_export import markdown_to_html
from pm_agent_system.pricing import estimate_cost, format_cost_summary
from pm_agent_system.models import (
    VALID_TARGET_TOOLS,
    BRDOutput,
    CodingPromptOutput,
    PRFAQOutput,
    ResearchOutput,
)
from pm_agent_system.utils import (
    export_jira_csv,
    export_linear_markdown,
    formatted_spec_extension,
    render_brd_to_markdown,
    render_build_spec_to_markdown,
    render_prfaq_to_markdown,
    render_research_to_markdown,
)
from pm_agent_system.vault import (
    generate_index_note,
    get_initiative,
    get_product_slug,
    get_vault_config,
    resolve_artifact_path,
    strip_frontmatter,
    write_revision_to_vault,
    write_to_vault,
)

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

import webbrowser

logger = logging.getLogger(__name__)

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


def _vault_for_inputs(inputs: dict):
    """Return (vault_config, product_slug) with initiative set, or (None, '')."""
    vault_cfg = get_vault_config()
    if not vault_cfg:
        return None, ""
    vault_cfg.initiative = get_initiative(inputs)
    return vault_cfg, get_product_slug(inputs)


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
        except Exception as exc:
            logger.warning("Failed to archive %s: %s", entry.name, exc)
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
    html_path = path.with_suffix(".html")
    html_path.write_text(markdown_to_html(markdown, title="Research Brief"), encoding="utf-8")
    return path


def save_prfaq(markdown: str, feature_summary: str, version: str) -> Path:
    """Write a PRFAQ markdown file with the version-aware filename convention."""
    slug = _slugify(feature_summary) or "prfaq"
    path = _output_dir() / f"prfaq_{slug}_v{version}.md"
    path.write_text(markdown, encoding="utf-8")
    html_path = path.with_suffix(".html")
    html_path.write_text(markdown_to_html(markdown, title="PRFAQ"), encoding="utf-8")
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
    html_path = path.with_suffix(".html")
    html_path.write_text(markdown_to_html(markdown, title="Business Requirements Document"), encoding="utf-8")
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


def save_brd_exports(brd: BRDOutput, label: str) -> None:
    """Write Jira CSV and Linear markdown exports alongside the BRD."""
    slug = _slugify(label) or "brd"
    out = _output_dir()
    jira_path = out / f"brd_{slug}_jira_import.csv"
    linear_path = out / f"brd_{slug}_linear_import.md"
    jira_path.write_text(export_jira_csv(brd), encoding="utf-8")
    linear_path.write_text(export_linear_markdown(brd), encoding="utf-8")
    print(f"Jira import CSV: {jira_path}")
    print(f"Linear import MD: {linear_path}")


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

    # Vault integration
    vault_cfg, product_slug = _vault_for_inputs(inputs)
    if vault_cfg:
        write_to_vault(markdown, "research_brief", product_slug, "1.0", vault_cfg,
                       downstream="prfaq")
        generate_index_note(product_slug, vault_cfg, input_path=args.input_file)

    if publish_dir:
        try:
            published = publish_output(working_copy, publish_dir, inputs["feature_summary"])
            print(f"Published approved brief to: {published}")
        except Exception as e:
            print(f"Warning: Failed to publish to {publish_dir}: {e}")

    if getattr(args, "open", False):
        html_path = working_copy.with_suffix(".html")
        if html_path.exists():
            webbrowser.open(html_path.resolve().as_uri())


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

    # Vault integration
    vault_cfg, product_slug = _vault_for_inputs(inputs)
    if vault_cfg:
        write_to_vault(markdown, "prfaq", product_slug, initial_version, vault_cfg,
                       upstream="research_brief", downstream="brd")
        generate_index_note(product_slug, vault_cfg, input_path=args.input_file)

    if publish_dir:
        try:
            published = publish_output(working_copy, publish_dir, inputs["feature_summary"])
            print(f"Published approved PRFAQ to: {published}")
        except Exception as e:
            print(f"Warning: Failed to publish to {publish_dir}: {e}")

    if getattr(args, "open", False):
        html_path = working_copy.with_suffix(".html")
        if html_path.exists():
            webbrowser.open(html_path.resolve().as_uri())


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

    # Vault read resolution: prefer vault copy if PM edited it there
    vault_cfg = get_vault_config()
    if vault_cfg:
        fm = read_frontmatter(prfaq_path)
        slug = fm.get("product_slug") or re.sub(r"_v\d+\.\d+$", "", prfaq_path.stem.replace("prfaq_", ""))
        vault_cfg.initiative = fm.get("initiative", "")
        try:
            resolved = resolve_artifact_path("prfaq", slug, vault_cfg, str(prfaq_path))
            prfaq_path = Path(resolved)
        except FileNotFoundError:
            pass  # fall through to the user-provided path

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

    # Vault integration — write revision as new version
    vault_cfg = get_vault_config()
    if vault_cfg:
        product_slug = fm.get("product_slug") or label.lower().replace("_", "-")
        vault_cfg.initiative = fm.get("initiative", "")
        write_revision_to_vault(markdown, "prfaq", product_slug, vault_cfg,
                                upstream="research_brief", downstream="brd")
        generate_index_note(product_slug, vault_cfg)


# ---------- Subcommand: full-pipeline (Agents 1 → 2 → 3) ----------


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
        "BRDOutput": "BRD Agent",
        "CodingPromptOutput": "BRD Agent",  # build spec runs on the same agent
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
            "BRD Agent": "brd",
        }.get(agent_name)
        if artifact_key and artifact_key in checkpoint.get("artifacts", {}):
            checkpoint["artifacts"][artifact_key]["tokens_in"] = usage["input_tokens"]
            checkpoint["artifacts"][artifact_key]["tokens_out"] = usage["output_tokens"]
            checkpoint["artifacts"][artifact_key]["estimated_cost_usd"] = round(cost, 4)
    save_checkpoint(output_dir, checkpoint)


def _save_artifact_from_task_output(task_output, label, slug, output_dir, checkpoint,
                                    vault_config=None, product_slug=None):
    """Inspect a single task output, save its artifact to disk, and update the checkpoint.

    Returns the artifact name if one was saved, else None.
    """
    if not hasattr(task_output, "pydantic") or task_output.pydantic is None:
        return None

    obj = task_output.pydantic

    if isinstance(obj, ResearchOutput):
        md = render_research_to_markdown(obj)
        path = save_markdown_brief(md)
        print(f"Research brief saved to: {path}")
        record_artifact(checkpoint, "research_brief", str(path))
        save_checkpoint(output_dir, checkpoint)
        if vault_config and product_slug:
            write_to_vault(md, "research_brief", product_slug, "1.0", vault_config,
                           downstream="prfaq")
        return "research_brief"

    if isinstance(obj, PRFAQOutput):
        version = obj.version_history[-1].version if obj.version_history else "1.0"
        md = render_prfaq_to_markdown(obj, slug=slug)
        path = save_prfaq(md, label, version)
        print(f"PRFAQ saved to: {path}")
        record_artifact(checkpoint, "prfaq", str(path))
        save_checkpoint(output_dir, checkpoint)
        if vault_config and product_slug:
            write_to_vault(md, "prfaq", product_slug, version, vault_config,
                           upstream="research_brief", downstream="brd")
        return "prfaq"

    if isinstance(obj, BRDOutput):
        version = obj.version_history[-1].version if obj.version_history else "1.0"
        md = render_brd_to_markdown(obj, slug=slug)
        path = save_brd(md, label, version)
        print(f"BRD saved to: {path}")
        save_brd_exports(obj, label)
        record_artifact(checkpoint, "brd", str(path))
        save_checkpoint(output_dir, checkpoint)
        if vault_config and product_slug:
            write_to_vault(md, "brd", product_slug, version, vault_config,
                           upstream="prfaq", downstream="build_spec")
        return "brd"

    return None


def cmd_full_pipeline(args: argparse.Namespace) -> None:
    inputs = validate_input(load_input(args.input_file))
    publish_dir = validate_publish_destination(inputs.get("publish_destination", ""))

    target_tool = (args.target_tool or os.getenv("DEFAULT_TARGET_TOOL", "kiro")).strip()
    if target_tool not in VALID_TARGET_TOOLS:
        print(f"Error: --target-tool must be one of {VALID_TARGET_TOOLS}")
        sys.exit(1)

    requirements_path_arg = ""
    if getattr(args, "requirements_path", None):
        reqp = Path(args.requirements_path).expanduser().resolve()
        if not reqp.exists():
            print(f"Error: Requirements file not found: {reqp}")
            sys.exit(1)
        requirements_path_arg = str(reqp)

    label = inputs["feature_summary"]
    slug = _slugify(label)
    output_dir = _output_dir()
    input_hash = compute_input_hash(args.input_file)

    # --fresh: delete any existing checkpoint
    if getattr(args, "fresh", False):
        delete_checkpoint(output_dir)

    # --resume: check for a resumable checkpoint
    resume = getattr(args, "resume", False)
    done = set()
    if resume:
        existing = load_checkpoint(output_dir)
        if existing is not None:
            if existing.get("input_hash") != input_hash:
                print("Warning: Input has changed since last run — starting fresh.")
            else:
                done = completed_stages(existing)
                if done:
                    print(f"Resuming. Already completed: {', '.join(sorted(done))}")

    # Determine what to run
    need_research = "research_brief" not in done
    need_prfaq = "prfaq" not in done
    need_brd = "brd" not in done

    if not need_research and not need_prfaq and not need_brd:
        print("All artifacts already present from a prior run. Nothing to do.")
        print("Use --fresh to force a full re-run.")
        delete_checkpoint(output_dir)
        return

    # Initialize or re-use checkpoint
    if done:
        checkpoint = load_checkpoint(output_dir) or new_checkpoint(input_hash, _MODEL)
    else:
        checkpoint = new_checkpoint(input_hash, _MODEL)
        save_checkpoint(output_dir, checkpoint)

    # Vault integration setup
    vault_cfg, product_slug = _vault_for_inputs(inputs)

    crew_inputs = {k: v for k, v in inputs.items() if k != "publish_destination"}
    crew_inputs.update({
        "prfaq_path": "",
        "research_path": "",
        "requirements_path": requirements_path_arg,
        "brd_path": "",
        "target_tool": target_tool,
    })
    skip = getattr(args, "skip_validation", False)

    # --- Resume path: only Agent 3 (BRD + build spec) ---
    if not need_research and not need_prfaq and need_brd:
        print(f"\nResuming Agent 3 (BRD + build spec) for: {label[:80]}...")

        # Find the PRFAQ and research paths from the checkpoint
        existing_ckpt = load_checkpoint(output_dir) or {}
        prfaq_file = existing_ckpt.get("artifacts", {}).get("prfaq", {}).get("path", "")
        research_file = existing_ckpt.get("artifacts", {}).get("research_brief", {}).get("path", "")
        # Vault read resolution: prefer vault copies if PM edited them
        if vault_cfg and product_slug:
            try:
                prfaq_file = resolve_artifact_path("prfaq", product_slug, vault_cfg, prfaq_file)
            except FileNotFoundError:
                pass
            try:
                research_file = resolve_artifact_path("research_brief", product_slug, vault_cfg, research_file)
            except FileNotFoundError:
                pass
        crew_inputs["prfaq_path"] = prfaq_file
        crew_inputs["research_path"] = research_file

        try:
            result = PmAgentSystem().brd_from_prfaq_crew().kickoff(inputs=crew_inputs)
        except Exception as e:
            print(f"\nError running Agent 3: {e}")
            sys.exit(1)

        # Save BRD from tasks_output
        if hasattr(result, "tasks_output"):
            for to in result.tasks_output:
                if hasattr(to, "pydantic") and isinstance(to.pydantic, BRDOutput):
                    brd_version = to.pydantic.version_history[-1].version if to.pydantic.version_history else "1.0"
                    brd_md = render_brd_to_markdown(to.pydantic, slug=slug)
                    brd_path = save_brd(brd_md, label, brd_version)
                    print(f"BRD saved to: {brd_path}")
                    save_brd_exports(to.pydantic, label)
                    record_artifact(checkpoint, "brd", str(brd_path))
                    save_checkpoint(output_dir, checkpoint)
                    if vault_cfg and product_slug:
                        write_to_vault(brd_md, "brd", product_slug, brd_version, vault_cfg,
                                       upstream="prfaq", downstream="build_spec")
                    break

        spec = extract_pydantic_output(result, CodingPromptOutput)
        if spec is None:
            print("\nError: Agent 3 did not return a valid CodingPromptOutput.")
            sys.exit(1)

    else:
        # --- Full run (or partial resume that needs Agent 1+2) ---
        print(f"\nFull pipeline starting for: {label[:80]}...")
        if requirements_path_arg:
            print(f"Customer requirements: {Path(requirements_path_arg).name}")
        print(f"Target tool for build spec: {target_tool}")
        print("Human review checkpoints will pause after each agent.\n")

        def _task_callback(task_output):
            _save_artifact_from_task_output(task_output, label, slug, output_dir, checkpoint,
                                            vault_config=vault_cfg, product_slug=product_slug)

        try:
            crew = PmAgentSystem().full_pipeline_crew(skip_validation=skip)
            crew.task_callback = _task_callback
            result = crew.kickoff(inputs=crew_inputs)
        except Exception as e:
            print(f"\nError running crew: {e}")
            sys.exit(1)

        spec = extract_pydantic_output(result, CodingPromptOutput)
        if spec is None:
            print("\nError: pipeline did not return a valid CodingPromptOutput object.")
            print("Raw output:", result)
            sys.exit(1)

    # Save build spec (always the final output)
    reference_md = render_build_spec_to_markdown(spec, slug=slug)
    ref_path, spec_path = save_build_spec(reference_md, spec.formatted_spec, label, target_tool)
    print(f"Build spec reference saved to: {ref_path}")
    print(f"Tool-ready formatted spec saved to: {spec_path}")

    # Vault: write build spec and update dashboard
    if vault_cfg and product_slug:
        write_to_vault(reference_md, "build_spec", product_slug, "1.0", vault_cfg,
                       upstream="brd")
        generate_index_note(product_slug, vault_cfg, input_path=args.input_file)

    # Print cost summary
    _print_cost_summary(result, checkpoint, output_dir)

    # Pipeline complete — delete checkpoint
    delete_checkpoint(output_dir)

    if publish_dir:
        try:
            publish_output(spec_path, publish_dir, f"{label}_{target_tool}")
            print(f"Published formatted spec to: {publish_dir}")
        except Exception as e:
            print(f"Warning: publish failed: {e}")

    # --open: launch the final HTML artifact in the default browser
    if getattr(args, "open", False):
        # Find the most recently written BRD HTML, falling back to the build spec
        html_candidates = sorted(output_dir.glob("brd_*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not html_candidates:
            html_candidates = sorted(output_dir.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
        if html_candidates:
            webbrowser.open(html_candidates[0].resolve().as_uri())


# ---------- Subcommand: brd (Agent 3, BRD + build spec from approved PRFAQ) ----------


def cmd_brd(args: argparse.Namespace) -> None:
    inputs = validate_input(load_input(args.input_file))
    prfaq_path = Path(args.prfaq_path).expanduser().resolve()
    if not prfaq_path.exists():
        print(f"Error: PRFAQ file not found: {prfaq_path}")
        sys.exit(1)

    # Vault read resolution: prefer vault copy if PM edited it there
    vault_cfg, product_slug = _vault_for_inputs(inputs)
    if vault_cfg and product_slug:
        try:
            prfaq_path = Path(resolve_artifact_path("prfaq", product_slug, vault_cfg, str(prfaq_path)))
        except FileNotFoundError:
            pass

    research_path_arg = ""
    if args.research_path:
        rp = Path(args.research_path).expanduser().resolve()
        if not rp.exists():
            print(f"Error: Research file not found: {rp}")
            sys.exit(1)
        research_path_arg = str(rp)

    requirements_path_arg = ""
    if args.requirements_path:
        reqp = Path(args.requirements_path).expanduser().resolve()
        if not reqp.exists():
            print(f"Error: Requirements file not found: {reqp}")
            sys.exit(1)
        requirements_path_arg = str(reqp)

    target_tool = (args.target_tool or os.getenv("DEFAULT_TARGET_TOOL", "kiro")).strip()
    if target_tool not in VALID_TARGET_TOOLS:
        print(f"Error: --target-tool must be one of {VALID_TARGET_TOOLS}")
        sys.exit(1)

    crew_inputs = {k: v for k, v in inputs.items() if k != "publish_destination"}
    crew_inputs.update({
        "prfaq_path": str(prfaq_path),
        "research_path": research_path_arg,
        "requirements_path": requirements_path_arg,
        "brd_path": "",
        "target_tool": target_tool,
    })

    print(f"\nGenerating BRD + build spec from PRFAQ: {prfaq_path.name}")
    if requirements_path_arg:
        print(f"Customer requirements: {Path(requirements_path_arg).name}")
    print(f"Target tool: {target_tool}\n")

    try:
        result = PmAgentSystem().brd_from_prfaq_crew().kickoff(inputs=crew_inputs)
    except Exception as e:
        print(f"\nError running crew: {e}")
        sys.exit(1)

    label = inputs["feature_summary"]
    slug = _slugify(label)
    vault_cfg, product_slug = _vault_for_inputs(inputs)

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
                save_brd_exports(task_output.pydantic, label)
                if vault_cfg and product_slug:
                    write_to_vault(brd_md, "brd", product_slug, brd_version, vault_cfg,
                                   upstream="prfaq", downstream="build_spec")

    spec = extract_pydantic_output(result, CodingPromptOutput)
    if spec is None:
        print("\nError: did not return a valid CodingPromptOutput.")
        sys.exit(1)
    reference_md = render_build_spec_to_markdown(spec, slug=slug)
    ref_path, spec_path = save_build_spec(reference_md, spec.formatted_spec, label, target_tool)
    print(f"Build spec reference: {ref_path}")
    print(f"Formatted spec:       {spec_path}")

    if vault_cfg and product_slug:
        write_to_vault(reference_md, "build_spec", product_slug, "1.0", vault_cfg,
                       upstream="brd")
        generate_index_note(product_slug, vault_cfg, input_path=args.input_file)

    if getattr(args, "open", False):
        html_candidates = sorted(_output_dir().glob("brd_*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
        if html_candidates:
            webbrowser.open(html_candidates[0].resolve().as_uri())


# ---------- Subcommand: build-spec (Agent 3 Mode 3) ----------


def cmd_build_spec(args: argparse.Namespace) -> None:
    brd_path = Path(args.brd_path).expanduser().resolve()
    if not brd_path.exists():
        print(f"Error: BRD file not found: {brd_path}")
        sys.exit(1)

    # Vault read resolution: prefer vault copy if PM edited it there
    vault_cfg = get_vault_config()
    if vault_cfg:
        fm = read_frontmatter(brd_path)
        slug = fm.get("product_slug") or re.sub(r"_v\d+\.\d+$", "", brd_path.stem.replace("brd_", ""))
        vault_cfg.initiative = fm.get("initiative", "")
        try:
            brd_path = Path(resolve_artifact_path("brd", slug, vault_cfg, str(brd_path)))
        except FileNotFoundError:
            pass

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

    # Vault integration
    vault_cfg = get_vault_config()
    if vault_cfg:
        product_slug = fm.get("product_slug") or label.lower().replace("_", "-")
        vault_cfg.initiative = fm.get("initiative", "")
        write_to_vault(reference_md, "build_spec", product_slug, "1.0", vault_cfg,
                       upstream="brd")
        generate_index_note(product_slug, vault_cfg)


# ---------- Subcommand: revise-brd (Agent 3 Mode 2) ----------


def cmd_revise_brd(args: argparse.Namespace) -> None:
    if not args.context_path and not args.context_text:
        print("Error: revise-brd requires at least one of --context-path or --context-text.")
        sys.exit(1)

    brd_path = Path(args.brd_path).expanduser().resolve()
    if not brd_path.exists():
        print(f"Error: BRD file not found: {brd_path}")
        sys.exit(1)

    # Vault read resolution: prefer vault copy if PM edited it there
    vault_cfg = get_vault_config()
    if vault_cfg:
        fm_pre = read_frontmatter(brd_path)
        slug = fm_pre.get("product_slug") or re.sub(r"_v\d+\.\d+$", "", brd_path.stem.replace("brd_", ""))
        vault_cfg.initiative = fm_pre.get("initiative", "")
        try:
            brd_path = Path(resolve_artifact_path("brd", slug, vault_cfg, str(brd_path)))
        except FileNotFoundError:
            pass

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
    save_brd_exports(brd, label)

    # Vault integration — write revision as new version
    vault_cfg = get_vault_config()
    if vault_cfg:
        product_slug = fm.get("product_slug") or label.lower().replace("_", "-")
        vault_cfg.initiative = fm.get("initiative", "")
        write_revision_to_vault(markdown, "brd", product_slug, vault_cfg,
                                upstream="prfaq", downstream="build_spec")
        generate_index_note(product_slug, vault_cfg)


# ---------- Subcommand: diff ----------


def cmd_diff(args: argparse.Namespace) -> None:
    """Show section-level changes between two document versions."""
    from pm_agent_system.utils.diff_versions import diff_markdown_versions

    old = Path(args.old_path).expanduser().resolve()
    new = Path(args.new_path).expanduser().resolve()
    if not old.exists():
        print(f"Error: File not found: {old}")
        sys.exit(1)
    if not new.exists():
        print(f"Error: File not found: {new}")
        sys.exit(1)
    print(diff_markdown_versions(str(old), str(new)))


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
        print(
            f"This will permanently delete all {len(files)} archived output "
            f"files in {archive}. This cannot be undone."
        )
        confirm = input("Type 'yes' to confirm: ").strip()
        if confirm != "yes":
            print("Aborted. No files were deleted.")
            return
        deleted = 0
        freed_bytes = 0
        for p in files:
            try:
                size = p.stat().st_size
                p.unlink()
                deleted += 1
                freed_bytes += size
            except Exception as e:
                print(f"  failed to delete {p.name}: {e}")
        freed_mb = freed_bytes / (1024 * 1024)
        print(f"Deleted {deleted} files from archive ({freed_mb:.2f} MB freed).")
        return

    if args.archive:
        days = _retention_days()
        moved = enforce_retention_policy(output_dir, archive_after_days=days)
        print(f"Archived {moved} files older than {days} days to {archive}.")
        return

    print("Nothing to do. Use --list, --archive, or --delete-archive.")


def cmd_view(args: argparse.Namespace) -> None:
    """Launch the TUI artifact viewer."""
    try:
        from pm_agent_system.viewer import ArtifactViewer
    except ImportError:
        print(
            "The viewer requires the [ui] extra. Install it with:\n"
            "  uv pip install 'pm-working-backwards-agent[ui]'"
        )
        return

    if args.serve:
        try:
            from textual_serve.server import Server
        except ImportError:
            print(
                "Browser mode requires textual-serve. Install it with:\n"
                "  uv pip install textual-serve"
            )
            return
        server = Server(
            f"python -m pm_agent_system.viewer {args.file or ''}",
            host="localhost",
            port=args.port,
        )
        print(f"Serving viewer at http://localhost:{args.port}")
        server.serve()
    else:
        app = ArtifactViewer(initial_file=args.file)
        app.run()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pm_agent_system")
    sub = parser.add_subparsers(dest="command", required=True)

    p_research = sub.add_parser("research", help="Run Agent 1 only (research brief)")
    p_research.add_argument("input_file", help="Path to YAML or JSON input file")
    p_research.add_argument("--skip-validation", action="store_true", help="Skip the pre-research challenge questions")
    p_research.add_argument("--open", action="store_true", help="Open the HTML artifact in the default browser when done")
    p_research.set_defaults(func=cmd_research)

    p_generate = sub.add_parser(
        "generate", help="Run Agent 1 then Agent 2 to produce a PRFAQ v1.0"
    )
    p_generate.add_argument("input_file", help="Path to YAML or JSON input file")
    p_generate.add_argument("--skip-validation", action="store_true", help="Skip the pre-research challenge questions")
    p_generate.add_argument("--open", action="store_true", help="Open the HTML artifact in the default browser when done")
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
    p_full.add_argument(
        "--requirements-path",
        help="Optional path to customer requirements file (CSV, Excel, Markdown, or Word)",
    )
    p_full.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the last checkpoint if input hasn't changed",
    )
    p_full.add_argument(
        "--fresh",
        action="store_true",
        help="Delete any existing checkpoint and run everything from scratch",
    )
    p_full.add_argument("--open", action="store_true", help="Open the final HTML artifact in the default browser when done")
    p_full.set_defaults(func=cmd_full_pipeline)

    p_brd = sub.add_parser(
        "brd",
        help="Run Agent 3 only — generate BRD + build spec from an approved PRFAQ",
    )
    p_brd.add_argument("input_file", help="Path to original YAML/JSON input (for context)")
    p_brd.add_argument("--prfaq-path", required=True, help="Path to approved PRFAQ markdown")
    p_brd.add_argument("--research-path", help="Optional path to research brief markdown")
    p_brd.add_argument(
        "--requirements-path",
        help="Optional path to customer requirements file (CSV, Excel, Markdown, or Word)",
    )
    p_brd.add_argument("--target-tool", choices=VALID_TARGET_TOOLS)
    p_brd.add_argument("--open", action="store_true", help="Open the HTML artifact in the default browser when done")
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

    p_diff = sub.add_parser(
        "diff",
        help="Compare two document versions section by section",
        description=(
            "Compare two document versions section by section. "
            "Note: Section matching uses exact header text. If you renamed a "
            "section header between versions, the diff will show it as a "
            "deletion and addition rather than a modification."
        ),
    )
    p_diff.add_argument("old_path", help="Path to the older version")
    p_diff.add_argument("new_path", help="Path to the newer version")
    p_diff.set_defaults(func=cmd_diff)

    # ----- Viewer -----

    p_view = sub.add_parser(
        "view",
        help="Open the TUI artifact viewer (requires: uv pip install 'pm-working-backwards-agent[ui]')",
    )
    p_view.add_argument(
        "file", nargs="?", default=None, help="Optional markdown file to open immediately"
    )
    p_view.add_argument(
        "--serve",
        action="store_true",
        help="Serve the viewer in a web browser instead of the terminal",
    )
    p_view.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for --serve mode (default: 8000)",
    )
    p_view.set_defaults(func=cmd_view)

    return parser


def run():
    """CLI entry point."""
    load_dotenv()
    parser = _build_parser()
    args = parser.parse_args()
    if args.command not in ("clean", "diff"):
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
    example_path = Path(__file__).parent.parent.parent / "examples" / "input.yaml"
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
