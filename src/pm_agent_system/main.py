#!/usr/bin/env python
"""CLI entry point for the PM Agent System.

Usage:
    # Agent 1 only — research brief (markdown input recommended; YAML also accepted)
    pm_agent_system research examples/input-brief-example.md

    # Full pipeline — research → PRFAQ generate (Mode 1)
    pm_agent_system generate examples/input-brief-example.md

    # Agent 2 only — revise an existing PRFAQ (Mode 2)
    pm_agent_system revise --prfaq-path output/prfaq_foo_v1.0.md \\
        --context-path notes/legal_feedback.md
    pm_agent_system revise --prfaq-path output/prfaq_foo_v1.0.md \\
        --context-text "Legal wants GDPR language in the CX section"
"""

import argparse
import logging
import os
import re
import shutil
import sys
import time
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
from pm_agent_system.input_parser import parse_input
from pm_agent_system.pricing import estimate_cost, format_cost_summary
from pm_agent_system.models import (
    VALID_TARGET_TOOLS,
    BRDOutput,
    CodingPromptOutput,
    DesignBriefOutput,
    PRFAQOutput,
    ResearchOutput,
)
from pm_agent_system.utils import (
    export_jira_csv,
    export_linear_markdown,
    formatted_spec_extension,
    render_brd_to_markdown,
    render_build_spec_to_markdown,
    render_design_brief_to_markdown,
    render_prfaq_to_markdown,
    render_research_to_markdown,
)
from pm_agent_system.vault import (
    copy_input_brief_to_vault,
    generate_index_note,
    get_initiative,
    get_product_slug,
    get_vault_config,
    mark_superseded,
    resolve_artifact_path,
    strip_frontmatter,
    write_revision_to_vault,
    write_to_vault,
)
from pm_agent_system.vault_checkpoint import (
    ArtifactHandler,
    VaultCheckpointProvider,
    WrittenArtifact,
    build_registry,
)
from crewai.core.providers.human_input import reset_provider, set_provider

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

import webbrowser

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["feature_summary", "goals", "timing", "user_summary"]
ENCOURAGED_FIELDS = ["success_metrics", "known_constraints", "internal_context", "business_context"]
OPTIONAL_FIELDS = ["publish_destination"]


# ---------- Input loading & validation ----------


def load_input(file_path: str) -> dict:
    """Load PM input from a YAML or markdown file (deprecated alias for parse_input)."""
    try:
        return parse_input(file_path)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)


def validate_input(inputs: dict) -> dict:
    """Validate required fields and set defaults for encouraged/optional fields.

    Tolerates ``None`` values in addition to missing keys: ``parse_markdown_input``
    returns ``None`` for a section whose header exists but has no content, and
    treating that the same as a missing field keeps the packaged example and
    any PM-authored brief with blank optional sections working.
    """
    missing = [f for f in REQUIRED_FIELDS if not (inputs.get(f) or "").strip()]
    if missing:
        print(f"Error: Missing required fields: {', '.join(missing)}")
        print("Please fill in these fields in your input file before running.")
        sys.exit(1)

    for field in ENCOURAGED_FIELDS:
        if not (inputs.get(field) or "").strip():
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


# ---------- Checkpoint provider helpers ----------

# Maps Pydantic output classes to their artifact_type label, used by the few
# post-kickoff hooks that need to know which artifact a TaskOutput corresponds to.
_PYDANTIC_TO_ARTIFACT: dict[type, str] = {
    ResearchOutput: "research_brief",
    PRFAQOutput: "prfaq",
    DesignBriefOutput: "design_brief",
    BRDOutput: "brd",
    CodingPromptOutput: "build_spec",
}


def _install_checkpoint_provider(
    handlers: list[ArtifactHandler],
    vault_cfg,
    product_slug: str,
):
    """Build and install the VaultCheckpointProvider. Returns (provider, token).

    Callers must call ``reset_provider(token)`` (or rely on try/finally) when done.
    """
    provider = VaultCheckpointProvider(
        registry=build_registry(handlers),
        vault_config=vault_cfg,
        product_slug=product_slug,
    )
    token = set_provider(provider)
    return provider, token


def _prfaq_version_from_output(obj) -> str:
    """Resolve the version string from a PRFAQOutput's version_history."""
    return obj.version_history[-1].version if obj.version_history else "1.0"


def _brd_version_from_output(obj) -> str:
    return obj.version_history[-1].version if obj.version_history else "1.0"


def _prompt_wireframe_choice(vault_path: str, output_path: str) -> str:
    """Prompt the PM with the [g]/[b]/[s] wireframe choice.

    Returns one of ``"g"``, ``"b"``, or ``"s"``. Defaults to ``"s"`` in
    non-interactive contexts (EOFError) so the pipeline can still finish.
    """
    print()
    print("Design brief approved.")
    print()
    print("How would you like to proceed with visual wireframes?")
    print("  [g]  Generate wireframes (coming soon — not yet available)")
    print("  [b]  Take the design brief to an external tool (Claude Design, Figma, etc.)")
    print("  [s]  Skip wireframes and continue to BRD")
    print()
    while True:
        try:
            resp = input("Choice [g/b/s]: ").strip().lower()
        except EOFError:
            return "s"
        if not resp:
            continue
        head = resp[0]
        if head in ("g", "b", "s"):
            return head
        print("Please respond with g, b, or s.")


def _print_wireframe_response(
    choice: str, vault_path: str, output_path: str
) -> None:
    """Print the user-facing response for the chosen [g/b/s] option."""
    if choice == "g":
        print()
        print("SVG wireframe generation is not yet available. It will be added in a future update.")
        print()
        print("In the meantime, you can use the design brief with an external tool:")
        print("  - Claude Design (claude.ai/design) — paste the brief as your starting prompt")
        print("  - Figma — use the screen inventory as your artboard list")
        print("  - A human designer — share the brief as a creative brief")
        print()
        print("Design brief location:")
        if vault_path:
            print(f"  -> {vault_path}")
        if output_path:
            print(f"  -> {output_path}")
        print()
        print("Continuing to BRD generation...")
    elif choice == "b":
        print()
        print("Design brief ready for external tools:")
        if vault_path:
            print(f"  -> {vault_path}")
        if output_path:
            print(f"  -> {output_path}")
        print()
        print("You can use it with:")
        print("  - Claude Design (claude.ai/design) — paste the brief as your starting prompt")
        print("  - Figma — use the screen inventory as your artboard list")
        print("  - A human designer — share the brief as a creative brief")
        print()
        print("Continuing to BRD generation...")
    else:
        # [s] — no extra messaging; the pipeline simply continues
        print()
        print("Skipping wireframes; continuing to BRD generation without a design brief reference.")


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


def save_design_brief(markdown: str, label: str, version: str = "1.0") -> Path:
    """Write a design brief markdown file to OUTPUT_DIR."""
    slug = _slugify(label) or "design_brief"
    path = _output_dir() / f"design_brief_{slug}_v{version}.md"
    path.write_text(markdown, encoding="utf-8")
    html_path = path.with_suffix(".html")
    html_path.write_text(markdown_to_html(markdown, title="Design Brief"), encoding="utf-8")
    return path


def save_brd(markdown: str, label: str, version: str) -> Path:
    slug = _slugify(label) or "brd"
    path = _output_dir() / f"brd_{slug}_v{version}.md"
    path.write_text(markdown, encoding="utf-8")
    html_path = path.with_suffix(".html")
    html_path.write_text(markdown_to_html(markdown, title="Business Requirements Document"), encoding="utf-8")
    return path


def resolve_visual_style_guide_path(inputs: dict) -> str:
    """Return the visual style guide path to pass into crew inputs.

    Priority: input brief's ``visual_style_guide_path`` → env var
    ``VISUAL_STYLE_GUIDE_PATH`` → empty string. If the resolved path is
    set but the file does not exist, log a warning and return empty so
    Agent 3 falls back to defaults without crashing.
    """
    raw = (inputs.get("visual_style_guide_path") or "").strip()
    if not raw:
        raw = os.getenv("VISUAL_STYLE_GUIDE_PATH", "").strip()
    if not raw:
        return ""
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if not path.exists():
        logger.warning("Visual style guide path %s does not exist; proceeding without it.", path)
        print(f"Note: visual style guide not found at {path}; Agent 3 will use defaults.")
        return ""
    return str(path)


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
    inputs = validate_input(parse_input(args.input_file))

    publish_dir = validate_publish_destination(inputs.get("publish_destination", ""))
    if publish_dir:
        print(f"Approved briefs will publish to: {publish_dir}")

    print(f"\nStarting research for: {inputs['feature_summary'][:80]}...")
    print("The agent will pause for your review before finalizing.\n")

    crew_inputs = {k: v for k, v in inputs.items() if k != "publish_destination"}

    vault_cfg, product_slug = _vault_for_inputs(inputs)
    provider, token = _install_checkpoint_provider(
        handlers=[
            ArtifactHandler(
                artifact_type="research_brief",
                pydantic_class=ResearchOutput,
                render_fn=render_research_to_markdown,
                save_output_fn=lambda md, _obj: save_markdown_brief(md),
                version="1.0",
                downstream="prfaq",
            ),
        ],
        vault_cfg=vault_cfg,
        product_slug=product_slug,
    )

    skip = getattr(args, "skip_validation", False)
    try:
        try:
            t0 = time.monotonic()
            result = PmAgentSystem().research_crew(skip_validation=skip).kickoff(inputs=crew_inputs)
            elapsed = time.monotonic() - t0
        except Exception as e:
            print(f"\nError running crew: {e}")
            sys.exit(1)
    finally:
        reset_provider(token)

    _print_run_metrics(result, "research", elapsed, product_slug or "")

    research = extract_pydantic_output(result, ResearchOutput)
    if research is None:
        print("\nError: Agent did not return a valid ResearchOutput object.")
        print("Raw output:", result)
        sys.exit(1)

    record = provider.artifacts.get("research_brief")
    if record is None:
        # Provider didn't fire (e.g. no human_input in this crew) — fall back to
        # the old path so the command still produces an artifact.
        markdown = render_research_to_markdown(research)
        working_copy = save_markdown_brief(markdown)
        if vault_cfg:
            write_to_vault(markdown, "research_brief", product_slug, "1.0", vault_cfg,
                           downstream="prfaq")
    else:
        working_copy = record.output_path
    print(f"\nResearch complete. Working copy saved to: {working_copy}")

    if vault_cfg:
        copy_input_brief_to_vault(args.input_file, product_slug, vault_cfg)
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
    inputs = validate_input(parse_input(args.input_file))

    publish_dir = validate_publish_destination(inputs.get("publish_destination", ""))
    if publish_dir:
        print(f"Approved PRFAQs will publish to: {publish_dir}")

    print(f"\nStarting research + PRFAQ generation for: {inputs['feature_summary'][:80]}...")
    print("The agent will pause for review after research and again after the PRFAQ.\n")

    crew_inputs = {k: v for k, v in inputs.items() if k != "publish_destination"}

    label = inputs["feature_summary"]
    slug = _slugify(label)
    vault_cfg, product_slug = _vault_for_inputs(inputs)
    provider, token = _install_checkpoint_provider(
        handlers=[
            ArtifactHandler(
                artifact_type="research_brief",
                pydantic_class=ResearchOutput,
                render_fn=render_research_to_markdown,
                save_output_fn=lambda md, _obj: save_markdown_brief(md),
                version="1.0",
                downstream="prfaq",
            ),
            ArtifactHandler(
                artifact_type="prfaq",
                pydantic_class=PRFAQOutput,
                render_fn=lambda obj: render_prfaq_to_markdown(obj, slug=slug),
                save_output_fn=lambda md, obj: save_prfaq(md, label, _prfaq_version_from_output(obj)),
                version=_prfaq_version_from_output,
                upstream="research_brief",
                downstream="brd",
            ),
        ],
        vault_cfg=vault_cfg,
        product_slug=product_slug,
    )

    skip = getattr(args, "skip_validation", False)
    try:
        try:
            t0 = time.monotonic()
            result = PmAgentSystem().research_and_generate_crew(skip_validation=skip).kickoff(inputs=crew_inputs)
            elapsed = time.monotonic() - t0
        except Exception as e:
            print(f"\nError running crew: {e}")
            sys.exit(1)
    finally:
        reset_provider(token)

    _print_run_metrics(result, "generate", elapsed, product_slug or "")

    prfaq = extract_pydantic_output(result, PRFAQOutput)
    if prfaq is None:
        print("\nError: Agent 2 did not return a valid PRFAQOutput object.")
        print("Raw output:", result)
        sys.exit(1)

    record = provider.artifacts.get("prfaq")
    if record is None:
        initial_version = _prfaq_version_from_output(prfaq)
        markdown = render_prfaq_to_markdown(prfaq, slug=slug)
        working_copy = save_prfaq(markdown, label, initial_version)
        if vault_cfg:
            write_to_vault(markdown, "prfaq", product_slug, initial_version, vault_cfg,
                           upstream="research_brief", downstream="brd")
    else:
        working_copy = record.output_path
    print(f"\nPRFAQ complete. Working copy saved to: {working_copy}")

    if vault_cfg:
        copy_input_brief_to_vault(args.input_file, product_slug, vault_cfg)
        generate_index_note(product_slug, vault_cfg, input_path=args.input_file)

    if publish_dir:
        try:
            published = publish_output(working_copy, publish_dir, label)
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

    # Reuse the original slug from frontmatter when available so revisions stay grouped.
    fm = read_frontmatter(prfaq_path)
    label = fm.get("slug") or re.sub(r"_v\d+\.\d+$", "", prfaq_path.stem.replace("prfaq_", ""))
    product_slug = fm.get("product_slug") or label.lower().replace("_", "-")
    if vault_cfg:
        vault_cfg.initiative = fm.get("initiative", "")

    # post_approve: mark the old (pre-revision) vault file as superseded
    old_vault_file = ""
    if vault_cfg:
        candidate = Path(str(prfaq_path))
        if candidate.exists() and candidate.is_file() and "PM Agent" in str(candidate):
            old_vault_file = str(candidate)

    def _on_approve_prfaq(new_vault_path: str) -> None:
        if old_vault_file and old_vault_file != new_vault_path and Path(old_vault_file).exists():
            mark_superseded(old_vault_file, Path(new_vault_path).stem)

    provider, token = _install_checkpoint_provider(
        handlers=[
            ArtifactHandler(
                artifact_type="prfaq",
                pydantic_class=PRFAQOutput,
                render_fn=lambda obj: render_prfaq_to_markdown(obj, slug=label),
                save_output_fn=lambda md, obj: save_prfaq(
                    md, label, obj.version_history[-1].version if obj.version_history else next_version,
                ),
                version=lambda obj: obj.version_history[-1].version if obj.version_history else next_version,
                upstream="research_brief",
                downstream="brd",
                post_approve=_on_approve_prfaq,
            ),
        ],
        vault_cfg=vault_cfg,
        product_slug=product_slug,
    )

    try:
        try:
            result = PmAgentSystem().revise_prfaq_crew().kickoff(inputs=crew_inputs)
        except Exception as e:
            print(f"\nError running crew: {e}")
            sys.exit(1)
    finally:
        reset_provider(token)

    prfaq = extract_pydantic_output(result, PRFAQOutput)
    if prfaq is None:
        print("\nError: Agent 2 did not return a valid PRFAQOutput object.")
        print("Raw output:", result)
        sys.exit(1)

    record = provider.artifacts.get("prfaq")
    if record is None:
        # Provider didn't fire — fall back to legacy path so revision is still written
        output_version = prfaq.version_history[-1].version if prfaq.version_history else next_version
        markdown = render_prfaq_to_markdown(prfaq, slug=label)
        working_copy = save_prfaq(markdown, label, output_version)
        if vault_cfg:
            write_revision_to_vault(markdown, "prfaq", product_slug, vault_cfg,
                                    upstream="research_brief", downstream="brd")
    else:
        working_copy = record.output_path
    print(f"\nRevision complete. Working copy saved to: {working_copy}")

    if vault_cfg:
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
    import json
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
    log_path = _output_dir() / "usage_log.jsonl"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except OSError:
        pass  # Non-blocking; don't fail the command over logging


def _record_artifact_from_task_output(
    task_output,
    label,
    slug,
    output_dir,
    checkpoint,
    provider,
    vault_config=None,
    product_slug=None,
):
    """Update the resume checkpoint from a TaskOutput.

    Normal flow: the VaultCheckpointProvider has already written the artifact to
    output/ and the vault (handle_feedback fires BEFORE task_callback). In that
    case we just record the path that the provider wrote.

    Fallback flow: if the provider has no record for this artifact type (e.g. the
    crew ran without human_input, or a test mocked kickoff past the provider), we
    write the artifact here so the pipeline still produces files. This keeps the
    callback safe as a last-resort writer.

    Also handles BRD Jira/Linear exports which the provider does not produce.
    """
    if not hasattr(task_output, "pydantic") or task_output.pydantic is None:
        return None

    obj = task_output.pydantic
    artifact_type = _PYDANTIC_TO_ARTIFACT.get(type(obj))
    if artifact_type is None:
        return None

    record = provider.artifacts.get(artifact_type) if provider else None

    if record is None:
        # Provider didn't fire — fallback write so the pipeline still produces files.
        if isinstance(obj, ResearchOutput):
            md = render_research_to_markdown(obj)
            path = save_markdown_brief(md)
            if vault_config and product_slug:
                write_to_vault(md, "research_brief", product_slug, "1.0", vault_config,
                               downstream="prfaq")
        elif isinstance(obj, PRFAQOutput):
            version = _prfaq_version_from_output(obj)
            md = render_prfaq_to_markdown(obj, slug=slug)
            path = save_prfaq(md, label, version)
            if vault_config and product_slug:
                write_to_vault(md, "prfaq", product_slug, version, vault_config,
                               upstream="research_brief", downstream="design_brief")
        elif isinstance(obj, DesignBriefOutput):
            md = render_design_brief_to_markdown(obj, slug=slug)
            path = save_design_brief(md, label, "1.0")
            if vault_config and product_slug:
                write_to_vault(md, "design_brief", product_slug, "1.0", vault_config,
                               upstream="prfaq", downstream="brd")
        elif isinstance(obj, BRDOutput):
            version = _brd_version_from_output(obj)
            md = render_brd_to_markdown(obj, slug=slug)
            path = save_brd(md, label, version)
            save_brd_exports(obj, label)
            if vault_config and product_slug:
                write_to_vault(md, "brd", product_slug, version, vault_config,
                               upstream="prfaq", downstream="build_spec")
        else:
            return None
        record_artifact(checkpoint, artifact_type, str(path))
        save_checkpoint(output_dir, checkpoint)
        return artifact_type

    # Provider already wrote — record path, add exports where relevant.
    record_artifact(checkpoint, artifact_type, str(record.output_path))
    save_checkpoint(output_dir, checkpoint)

    if isinstance(obj, BRDOutput):
        try:
            save_brd_exports(obj, label)
        except Exception as exc:
            logger.warning("Failed to save BRD exports: %s", exc)

    return artifact_type


def cmd_full_pipeline(args: argparse.Namespace) -> None:
    inputs = validate_input(parse_input(args.input_file))
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
    skip_design = bool(getattr(args, "skip_design", False))
    need_research = "research_brief" not in done
    need_prfaq = "prfaq" not in done
    need_design = (not skip_design) and "design_brief" not in done
    need_brd = "brd" not in done

    if not need_research and not need_prfaq and not need_design and not need_brd:
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
        "design_brief_path": "",
        "visual_style_guide_path": resolve_visual_style_guide_path(inputs),
        "requirements_path": requirements_path_arg,
        "brd_path": "",
        "target_tool": target_tool,
    })
    skip = getattr(args, "skip_validation", False)

    # Holds the PM's [g/b/s] choice after design-brief approval so we can
    # optionally clear design_brief_path before the BRD task interpolates
    # its prompt.
    wireframe_choice: dict[str, str] = {"value": ""}

    def _on_approve_design_brief(new_vault_path: str) -> None:
        record = provider.artifacts.get("design_brief")
        out_path = str(record.output_path) if record else ""
        choice = _prompt_wireframe_choice(new_vault_path, out_path)
        wireframe_choice["value"] = choice
        _print_wireframe_response(choice, new_vault_path, out_path)
        if choice == "s":
            # BRD must not reference design brief — clear the path so the
            # conditional block in the BRD task skips it. The chained crew
            # still passes the DesignBriefOutput via context, so the agent
            # will see it, but the task prompt explicitly skips screen-ref
            # instructions when design_brief_path is empty.
            crew_inputs["design_brief_path"] = ""

    # Build the full registry — only the handlers for tasks that will actually run
    # are needed, but registering all four is harmless (unused classes never match).
    prfaq_downstream = "brd" if skip_design else "design_brief"
    brd_upstream = "prfaq" if skip_design else "design_brief"

    # Mutable cell holding the live BRDOutput once the BRD task completes.
    # Used by the build_spec handler below to append the deterministic STRIDE
    # stub and RACI matrix to spec.formatted_spec before save and render.
    brd_holder: dict[str, BRDOutput] = {}

    def _make_build_spec_render(original_render_fn):
        def _render(obj: CodingPromptOutput) -> str:
            brd_obj = brd_holder.get("brd")
            if brd_obj is not None:
                try:
                    from pm_agent_system.utils.render_build_spec import (
                        _augment_spec_with_stride_raci,
                    )
                    _augment_spec_with_stride_raci(obj, brd_obj)
                except Exception as exc:
                    logger.warning("STRIDE and RACI augmentation skipped: %s", exc)
            return original_render_fn(obj)
        return _render

    _build_spec_render_fn = _make_build_spec_render(
        lambda obj: render_build_spec_to_markdown(obj, slug=slug)
    )

    handlers = [
        ArtifactHandler(
            artifact_type="research_brief",
            pydantic_class=ResearchOutput,
            render_fn=render_research_to_markdown,
            save_output_fn=lambda md, _obj: save_markdown_brief(md),
            version="1.0",
            downstream="prfaq",
        ),
        ArtifactHandler(
            artifact_type="prfaq",
            pydantic_class=PRFAQOutput,
            render_fn=lambda obj: render_prfaq_to_markdown(obj, slug=slug),
            save_output_fn=lambda md, obj: save_prfaq(
                md, label, obj.version_history[-1].version if obj.version_history else "1.0"
            ),
            version=_prfaq_version_from_output,
            upstream="research_brief",
            downstream=prfaq_downstream,
        ),
    ]

    if not skip_design:
        handlers.append(
            ArtifactHandler(
                artifact_type="design_brief",
                pydantic_class=DesignBriefOutput,
                render_fn=lambda obj: render_design_brief_to_markdown(obj, slug=slug),
                save_output_fn=lambda md, _obj: save_design_brief(md, label, "1.0"),
                version="1.0",
                upstream="prfaq",
                downstream="brd",
                post_approve=_on_approve_design_brief,
            )
        )

    handlers.extend([
        ArtifactHandler(
            artifact_type="brd",
            pydantic_class=BRDOutput,
            render_fn=lambda obj: render_brd_to_markdown(obj, slug=slug),
            save_output_fn=lambda md, obj: save_brd(
                md, label, obj.version_history[-1].version if obj.version_history else "1.0"
            ),
            version=_brd_version_from_output,
            upstream=brd_upstream,
            downstream="build_spec",
        ),
        ArtifactHandler(
            artifact_type="build_spec",
            pydantic_class=CodingPromptOutput,
            render_fn=_build_spec_render_fn,
            save_output_fn=lambda md, obj: save_build_spec(md, obj.formatted_spec, label, target_tool),
            version="1.0",
            upstream="brd",
        ),
    ])
    provider, token = _install_checkpoint_provider(
        handlers=handlers, vault_cfg=vault_cfg, product_slug=product_slug,
    )

    # Pre-compute the expected design brief path so the BRD task can read it
    # when design_brief_path interpolation happens. If the PM picks [s] at the
    # post-approve prompt, we clear this before the BRD task runs.
    if not skip_design:
        crew_inputs["design_brief_path"] = str(
            _output_dir() / f"design_brief_{slug}_v1.0.md"
        )

    # --- Resume path: only Agent 4 (BRD + build spec) ---
    try:
        if not need_research and not need_prfaq and not need_design and need_brd:
            print(f"\nResuming Agent 4 (BRD + build spec) for: {label[:80]}...")

            # Find the PRFAQ, research, and (optional) design brief paths from the checkpoint
            existing_ckpt = load_checkpoint(output_dir) or {}
            prfaq_file = existing_ckpt.get("artifacts", {}).get("prfaq", {}).get("path", "")
            research_file = existing_ckpt.get("artifacts", {}).get("research_brief", {}).get("path", "")
            design_file = existing_ckpt.get("artifacts", {}).get("design_brief", {}).get("path", "")
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
                if design_file:
                    try:
                        design_file = resolve_artifact_path(
                            "design_brief", product_slug, vault_cfg, design_file
                        )
                    except FileNotFoundError:
                        pass
            crew_inputs["prfaq_path"] = prfaq_file
            crew_inputs["research_path"] = research_file
            crew_inputs["design_brief_path"] = design_file

            def _resume_task_callback(task_output):
                now = time.monotonic()
                task_name = (
                    getattr(task_output, "name", None)
                    or type(getattr(task_output, "pydantic", None)).__name__
                    or "unknown"
                )
                # Stash the BRDOutput so the build_spec render hook can append
                # the deterministic STRIDE stub and RACI matrix before save.
                if hasattr(task_output, "pydantic") and isinstance(task_output.pydantic, BRDOutput):
                    brd_holder["brd"] = task_output.pydantic
                # Absolute completion time from pipeline start.
                task_timings[task_name] = now - t0_pipeline
                _record_artifact_from_task_output(
                    task_output, label, slug, output_dir, checkpoint, provider,
                    vault_config=vault_cfg, product_slug=product_slug,
                )

            try:
                t0_pipeline = time.monotonic()
                task_timings: dict[str, float] = {"_last_completion_at": t0_pipeline}
                crew = PmAgentSystem().brd_from_prfaq_crew()
                crew.task_callback = _resume_task_callback
                result = crew.kickoff(inputs=crew_inputs)
                elapsed_pipeline = time.monotonic() - t0_pipeline
            except Exception as e:
                print(f"\nError running Agent 4: {e}")
                sys.exit(1)

            spec = extract_pydantic_output(result, CodingPromptOutput)
            if spec is None:
                print("\nError: Agent 4 did not return a valid CodingPromptOutput.")
                sys.exit(1)

        else:
            # --- Full run (or partial resume that needs Agent 1+2) ---
            print(f"\nFull pipeline starting for: {label[:80]}...")
            if requirements_path_arg:
                print(f"Customer requirements: {Path(requirements_path_arg).name}")
            print(f"Target tool for build spec: {target_tool}")
            print("Human review checkpoints will pause after each agent.\n")

            def _task_callback(task_output):
                now = time.monotonic()
                task_name = (
                    getattr(task_output, "name", None)
                    or type(getattr(task_output, "pydantic", None)).__name__
                    or "unknown"
                )
                # Stash the BRDOutput so the build_spec render hook can append
                # the deterministic STRIDE stub and RACI matrix before save.
                if hasattr(task_output, "pydantic") and isinstance(task_output.pydantic, BRDOutput):
                    brd_holder["brd"] = task_output.pydantic
                # Absolute completion time from pipeline start.
                # Under async execution, tasks complete out of order, so
                # absolute timestamps let us see overlap vs sequential.
                task_timings[task_name] = now - t0_pipeline
                _record_artifact_from_task_output(
                    task_output, label, slug, output_dir, checkpoint, provider,
                    vault_config=vault_cfg, product_slug=product_slug,
                )

            try:
                t0_pipeline = time.monotonic()
                task_timings: dict[str, float] = {"_last_completion_at": t0_pipeline}
                crew = PmAgentSystem().full_pipeline_crew(
                    skip_validation=skip, skip_design=skip_design
                )
                crew.task_callback = _task_callback
                result = crew.kickoff(inputs=crew_inputs)
                elapsed_pipeline = time.monotonic() - t0_pipeline
            except Exception as e:
                print(f"\nError running crew: {e}")
                sys.exit(1)

            spec = extract_pydantic_output(result, CodingPromptOutput)
            if spec is None:
                print("\nError: pipeline did not return a valid CodingPromptOutput object.")
                print("Raw output:", result)
                sys.exit(1)
    finally:
        reset_provider(token)

    # Build spec paths — provider already wrote both reference + formatted files
    bs_record = provider.artifacts.get("build_spec")
    if bs_record is not None:
        ref_path = bs_record.output_path
        spec_path = bs_record.extras[0] if bs_record.extras else ref_path
    else:
        # Fallback (e.g. human_input disabled): do what the old code did
        reference_md = render_build_spec_to_markdown(spec, slug=slug)
        ref_path, spec_path = save_build_spec(reference_md, spec.formatted_spec, label, target_tool)
        if vault_cfg and product_slug:
            write_to_vault(reference_md, "build_spec", product_slug, "1.0", vault_cfg,
                           upstream="brd")
    print(f"Build spec reference saved to: {ref_path}")
    print(f"Tool-ready formatted spec saved to: {spec_path}")

    if vault_cfg and product_slug:
        copy_input_brief_to_vault(args.input_file, product_slug, vault_cfg)
        generate_index_note(product_slug, vault_cfg, input_path=args.input_file)

    # Print cost summary
    _print_cost_summary(result, checkpoint, output_dir)

    # Print per-task wall-clock breakdown (populated by task callbacks)
    # Values are absolute completion timestamps from pipeline start.
    # For tasks with human_input=True (research_brief, prfaq, design_brief,
    # brd), we prefer the provider's llm_completion_at dict which captures
    # LLM output-ready time BEFORE the human approval prompt, so the PM's
    # review pause is NOT counted in the measured latency.
    timings_display = {k: v for k, v in task_timings.items() if not k.startswith("_")}
    # Merge in provider LLM timestamps, keyed by artifact type.
    # These map to task names via the handler registry.
    artifact_to_task_name = {
        "research_brief": "research_synthesis_task",
        "prfaq": "generate_prfaq",
        "design_brief": "generate_design_brief",
        "brd": "brd_assembly_task",
        "build_spec": "generate_build_spec_chained",
    }
    for artifact_type, monotonic_ts in provider.llm_completion_at.items():
        task_name = artifact_to_task_name.get(artifact_type, artifact_type)
        # Override the callback-captured time with the pre-prompt time.
        timings_display[task_name] = monotonic_ts - t0_pipeline

    if timings_display:
        # Sort by completion time so the output reads chronologically.
        sorted_items = sorted(timings_display.items(), key=lambda kv: kv[1])
        print("\nPer-task LLM completion time (seconds from pipeline start, review pauses excluded):")
        for name, sec in sorted_items:
            print(f"  {name}:  {sec:.1f}s")
    print(f"\nTotal pipeline elapsed (includes review pauses): {elapsed_pipeline:.1f}s")

    # Append to usage_log.jsonl for trend analysis
    import json as _json
    total_in = sum(u.get("input_tokens", 0) for u in _extract_agent_usage(result).values())
    total_out = sum(u.get("output_tokens", 0) for u in _extract_agent_usage(result).values())
    total_cost = estimate_cost(_MODEL, total_in, total_out)
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "command": "full-pipeline",
        "model": _MODEL,
        "input_tokens": total_in,
        "output_tokens": total_out,
        "estimated_cost_usd": round(total_cost, 4),
        "elapsed_seconds": round(elapsed_pipeline, 1),
        "product_slug": product_slug or "",
        "per_task_elapsed": {k: round(v, 1) for k, v in timings_display.items()},
        "skip_design": skip_design,
    }
    log_path = output_dir / "usage_log.jsonl"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(_json.dumps(log_entry) + "\n")
    except OSError:
        pass

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


# ---------- Subcommand: brd (Agent 4, BRD + build spec from approved PRFAQ) ----------


def cmd_brd(args: argparse.Namespace) -> None:
    inputs = validate_input(parse_input(args.input_file))
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

    # Resolve the design brief path: explicit --design-brief-path wins;
    # otherwise look for a latest vault copy; empty string means "no brief".
    design_brief_path_arg = ""
    if getattr(args, "design_brief_path", None):
        dp = Path(args.design_brief_path).expanduser().resolve()
        if not dp.exists():
            print(f"Error: Design brief file not found: {dp}")
            sys.exit(1)
        design_brief_path_arg = str(dp)
    elif vault_cfg and product_slug:
        try:
            resolved = resolve_artifact_path(
                "design_brief", product_slug, vault_cfg, ""
            )
            if resolved:
                design_brief_path_arg = resolved
        except FileNotFoundError:
            design_brief_path_arg = ""

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
        "design_brief_path": design_brief_path_arg,
        "requirements_path": requirements_path_arg,
        "brd_path": "",
        "target_tool": target_tool,
    })

    print(f"\nGenerating BRD + build spec from PRFAQ: {prfaq_path.name}")
    if design_brief_path_arg:
        print(f"Design brief:          {Path(design_brief_path_arg).name}")
    if requirements_path_arg:
        print(f"Customer requirements: {Path(requirements_path_arg).name}")
    print(f"Target tool: {target_tool}\n")

    label = inputs["feature_summary"]
    slug = _slugify(label)

    brd_upstream = "design_brief" if design_brief_path_arg else "prfaq"

    # Mutable cell holding the live BRDOutput once the BRD task completes.
    # Used by the build_spec handler below to append the deterministic STRIDE
    # stub and RACI matrix to spec.formatted_spec before save and render.
    brd_holder: dict[str, BRDOutput] = {}

    def _make_build_spec_render(original_render_fn):
        def _render(obj: CodingPromptOutput) -> str:
            brd_obj = brd_holder.get("brd")
            if brd_obj is not None:
                try:
                    from pm_agent_system.utils.render_build_spec import (
                        _augment_spec_with_stride_raci,
                    )
                    _augment_spec_with_stride_raci(obj, brd_obj)
                except Exception as exc:
                    logger.warning("STRIDE and RACI augmentation skipped: %s", exc)
            return original_render_fn(obj)
        return _render

    _build_spec_render_fn = _make_build_spec_render(
        lambda obj: render_build_spec_to_markdown(obj, slug=slug)
    )

    provider, token = _install_checkpoint_provider(
        handlers=[
            ArtifactHandler(
                artifact_type="brd",
                pydantic_class=BRDOutput,
                render_fn=lambda obj: render_brd_to_markdown(obj, slug=slug),
                save_output_fn=lambda md, obj: save_brd(
                    md, label, obj.version_history[-1].version if obj.version_history else "1.0",
                ),
                version=_brd_version_from_output,
                upstream=brd_upstream,
                downstream="build_spec",
            ),
            ArtifactHandler(
                artifact_type="build_spec",
                pydantic_class=CodingPromptOutput,
                render_fn=_build_spec_render_fn,
                save_output_fn=lambda md, obj: save_build_spec(md, obj.formatted_spec, label, target_tool),
                version="1.0",
                upstream="brd",
            ),
        ],
        vault_cfg=vault_cfg,
        product_slug=product_slug,
    )

    def _task_callback(task_output):
        # BRD needs Jira/Linear exports alongside the provider's disk writes.
        # We also stash the BRDOutput here so the build_spec render hook above
        # can append STRIDE and RACI before the provider writes the spec.
        if hasattr(task_output, "pydantic") and isinstance(task_output.pydantic, BRDOutput):
            brd_holder["brd"] = task_output.pydantic
            try:
                save_brd_exports(task_output.pydantic, label)
            except Exception as exc:
                logger.warning("Failed to save BRD exports: %s", exc)

    try:
        try:
            t0 = time.monotonic()
            crew = PmAgentSystem().split_brd_crew()
            crew.task_callback = _task_callback
            result = crew.kickoff(inputs=crew_inputs)
            elapsed = time.monotonic() - t0
        except Exception as e:
            print(f"\nError running crew: {e}")
            sys.exit(1)
    finally:
        reset_provider(token)

    _print_run_metrics(result, "brd", elapsed, product_slug or "")

    # Confirm the final typed output was produced
    spec = extract_pydantic_output(result, CodingPromptOutput)
    if spec is None:
        print("\nError: did not return a valid CodingPromptOutput.")
        sys.exit(1)

    # Report BRD path from provider (or fallback)
    brd_record = provider.artifacts.get("brd")
    if brd_record is not None:
        print(f"BRD saved to: {brd_record.output_path}")
    else:
        # Fallback: provider didn't fire — do the old write
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

    # Report build spec paths
    bs_record = provider.artifacts.get("build_spec")
    if bs_record is not None:
        ref_path = bs_record.output_path
        spec_path = bs_record.extras[0] if bs_record.extras else ref_path
    else:
        reference_md = render_build_spec_to_markdown(spec, slug=slug)
        ref_path, spec_path = save_build_spec(reference_md, spec.formatted_spec, label, target_tool)
        if vault_cfg and product_slug:
            write_to_vault(reference_md, "build_spec", product_slug, "1.0", vault_cfg,
                           upstream="brd")
    print(f"Build spec reference: {ref_path}")
    print(f"Formatted spec:       {spec_path}")

    if vault_cfg and product_slug:
        copy_input_brief_to_vault(args.input_file, product_slug, vault_cfg)
        generate_index_note(product_slug, vault_cfg, input_path=args.input_file)

    if getattr(args, "open", False):
        html_candidates = sorted(_output_dir().glob("brd_*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
        if html_candidates:
            webbrowser.open(html_candidates[0].resolve().as_uri())


# ---------- Subcommand: build-spec (Agent 4 Mode 3) ----------


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

    fm = read_frontmatter(brd_path)
    label = fm.get("slug") or re.sub(r"_v\d+\.\d+$", "", brd_path.stem.replace("brd_", ""))
    product_slug = fm.get("product_slug") or label.lower().replace("_", "-")

    vault_cfg = get_vault_config()
    if vault_cfg:
        vault_cfg.initiative = fm.get("initiative", "")

    provider, token = _install_checkpoint_provider(
        handlers=[
            ArtifactHandler(
                artifact_type="build_spec",
                pydantic_class=CodingPromptOutput,
                render_fn=lambda obj: render_build_spec_to_markdown(obj, slug=label),
                save_output_fn=lambda md, obj: save_build_spec(md, obj.formatted_spec, label, target_tool),
                version="1.0",
                upstream="brd",
            ),
        ],
        vault_cfg=vault_cfg,
        product_slug=product_slug,
    )

    try:
        try:
            t0 = time.monotonic()
            result = PmAgentSystem().split_build_spec_crew().kickoff(inputs=crew_inputs)
            elapsed = time.monotonic() - t0
        except Exception as e:
            print(f"\nError running crew: {e}")
            sys.exit(1)
    finally:
        reset_provider(token)

    _print_run_metrics(result, "build-spec", elapsed, product_slug or "")

    # The split crew produces two outputs: BuildSpecStructureOutput and
    # FormattedSpecOutput. Extract both and merge into CodingPromptOutput.
    from pm_agent_system.models.build_spec_intermediate import (
        BuildSpecStructureOutput,
        FormattedSpecOutput,
    )
    structure = extract_pydantic_output(result, BuildSpecStructureOutput)
    fmt = extract_pydantic_output(result, FormattedSpecOutput)

    if structure is None:
        print("\nError: did not return a valid BuildSpecStructureOutput.")
        sys.exit(1)

    # Merge into CodingPromptOutput for the renderer
    from pm_agent_system.models import FeatureSpec, UserFlow
    spec = CodingPromptOutput(
        build_summary=structure.build_summary,
        user_flows=[
            UserFlow(name=uf.name, steps=uf.steps, related_requirements=uf.related_requirements)
            for uf in structure.user_flows
        ],
        feature_specs=[
            FeatureSpec(
                name=fs.name, description=fs.description,
                acceptance_criteria=fs.acceptance_criteria,
                priority=fs.priority, code_samples=fs.code_samples,
            )
            for fs in structure.feature_specs
        ],
        technical_constraints=structure.technical_constraints,
        architecture_reference=structure.architecture_reference,
        current_state_context=structure.current_state_context,
        out_of_scope=structure.out_of_scope,
        target_tool=structure.target_tool,
        formatted_spec=fmt.formatted_spec if fmt else "",
    )

    # Append deterministic STRIDE stub and RACI matrix after the LLM-produced
    # formatted_spec. The standalone build-spec flow has no live BRDOutput on
    # hand, so parse the three trigger signals out of the BRD markdown on disk.
    from pm_agent_system.utils.render_build_spec import (
        _augment_spec_with_stride_raci,
        extract_brd_trigger_state,
    )
    try:
        brd_markdown = brd_path.read_text(encoding="utf-8")
        trigger_state = extract_brd_trigger_state(brd_markdown)
        _augment_spec_with_stride_raci(spec, trigger_state)
    except Exception as exc:
        logger.warning(
            "STRIDE and RACI augmentation skipped for %s: %s", brd_path.name, exc
        )

    bs_record = provider.artifacts.get("build_spec")
    if bs_record is not None:
        ref_path = bs_record.output_path
        spec_path = bs_record.extras[0] if bs_record.extras else ref_path
    else:
        reference_md = render_build_spec_to_markdown(spec, slug=label)
        ref_path, spec_path = save_build_spec(reference_md, spec.formatted_spec, label, target_tool)
        if vault_cfg:
            write_to_vault(reference_md, "build_spec", product_slug, "1.0", vault_cfg,
                           upstream="brd")
    print(f"Build spec reference: {ref_path}")
    print(f"Formatted spec:       {spec_path}")

    if vault_cfg:
        generate_index_note(product_slug, vault_cfg)


# ---------- Subcommand: revise-brd (Agent 4 Mode 2) ----------


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

    fm = read_frontmatter(brd_path)
    label = fm.get("slug") or re.sub(r"_v\d+\.\d+$", "", brd_path.stem.replace("brd_", ""))
    product_slug = fm.get("product_slug") or label.lower().replace("_", "-")

    vault_cfg_for_provider = get_vault_config()
    if vault_cfg_for_provider:
        vault_cfg_for_provider.initiative = fm.get("initiative", "")

    old_vault_file = ""
    if vault_cfg_for_provider:
        candidate = Path(str(brd_path))
        if candidate.exists() and "PM Agent" in str(candidate):
            old_vault_file = str(candidate)

    def _on_approve_brd(new_vault_path: str) -> None:
        if old_vault_file and old_vault_file != new_vault_path and Path(old_vault_file).exists():
            mark_superseded(old_vault_file, Path(new_vault_path).stem)

    provider, token = _install_checkpoint_provider(
        handlers=[
            ArtifactHandler(
                artifact_type="brd",
                pydantic_class=BRDOutput,
                render_fn=lambda obj: render_brd_to_markdown(obj, slug=label),
                save_output_fn=lambda md, obj: save_brd(
                    md, label, obj.version_history[-1].version if obj.version_history else next_version,
                ),
                version=lambda obj: obj.version_history[-1].version if obj.version_history else next_version,
                upstream="prfaq",
                downstream="build_spec",
                post_approve=_on_approve_brd,
            ),
        ],
        vault_cfg=vault_cfg_for_provider,
        product_slug=product_slug,
    )

    try:
        try:
            result = PmAgentSystem().revise_brd_crew().kickoff(inputs=crew_inputs)
        except Exception as e:
            print(f"\nError running crew: {e}")
            sys.exit(1)
    finally:
        reset_provider(token)

    brd = extract_pydantic_output(result, BRDOutput)
    if brd is None:
        print("\nError: Agent 4 did not return a valid BRDOutput.")
        sys.exit(1)

    record = provider.artifacts.get("brd")
    if record is None:
        # Fallback (provider didn't fire)
        output_version = brd.version_history[-1].version if brd.version_history else next_version
        markdown = render_brd_to_markdown(brd, slug=label)
        working_copy = save_brd(markdown, label, output_version)
        if vault_cfg_for_provider:
            write_revision_to_vault(markdown, "brd", product_slug, vault_cfg_for_provider,
                                    upstream="prfaq", downstream="build_spec")
    else:
        working_copy = record.output_path
    print(f"\nRevision complete. Working copy saved to: {working_copy}")
    save_brd_exports(brd, label)

    if vault_cfg_for_provider:
        generate_index_note(product_slug, vault_cfg_for_provider)


# ---------- Subcommand: wireframes (Agent 3 standalone) ----------


def cmd_wireframes(args: argparse.Namespace) -> None:
    """Run Agent 3 only — generate a design brief from an approved PRFAQ on disk."""
    inputs = validate_input(parse_input(args.input_file))

    prfaq_path = Path(args.prfaq_path).expanduser().resolve()
    if not prfaq_path.exists():
        print(f"Error: PRFAQ file not found: {prfaq_path}")
        sys.exit(1)

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

    label = inputs["feature_summary"]
    slug = _slugify(label)

    crew_inputs = {k: v for k, v in inputs.items() if k != "publish_destination"}
    crew_inputs.update({
        "prfaq_path": str(prfaq_path),
        "research_path": research_path_arg,
        "design_brief_path": "",
        "visual_style_guide_path": resolve_visual_style_guide_path(inputs),
    })

    print(f"\nGenerating design brief from PRFAQ: {prfaq_path.name}")
    if crew_inputs["visual_style_guide_path"]:
        print(f"Visual style guide: {Path(crew_inputs['visual_style_guide_path']).name}")
    print()

    def _on_approve(new_vault_path: str) -> None:
        record = provider.artifacts.get("design_brief")
        out_path = str(record.output_path) if record else ""
        choice = _prompt_wireframe_choice(new_vault_path, out_path)
        _print_wireframe_response(choice, new_vault_path, out_path)

    provider, token = _install_checkpoint_provider(
        handlers=[
            ArtifactHandler(
                artifact_type="design_brief",
                pydantic_class=DesignBriefOutput,
                render_fn=lambda obj: render_design_brief_to_markdown(obj, slug=slug),
                save_output_fn=lambda md, _obj: save_design_brief(md, label, "1.0"),
                version="1.0",
                upstream="prfaq",
                downstream="brd",
                post_approve=_on_approve,
            ),
        ],
        vault_cfg=vault_cfg,
        product_slug=product_slug,
    )

    try:
        try:
            result = PmAgentSystem().design_brief_crew().kickoff(inputs=crew_inputs)
        except Exception as e:
            print(f"\nError running crew: {e}")
            sys.exit(1)
    finally:
        reset_provider(token)

    brief = extract_pydantic_output(result, DesignBriefOutput)
    if brief is None:
        print("\nError: Agent 3 did not return a valid DesignBriefOutput.")
        print("Raw output:", result)
        sys.exit(1)

    record = provider.artifacts.get("design_brief")
    if record is None:
        markdown = render_design_brief_to_markdown(brief, slug=slug)
        working_copy = save_design_brief(markdown, label, "1.0")
        if vault_cfg and product_slug:
            write_to_vault(markdown, "design_brief", product_slug, "1.0", vault_cfg,
                           upstream="prfaq", downstream="brd")
    else:
        working_copy = record.output_path
    print(f"\nDesign brief saved to: {working_copy}")

    if vault_cfg and product_slug:
        copy_input_brief_to_vault(args.input_file, product_slug, vault_cfg)
        generate_index_note(product_slug, vault_cfg, input_path=args.input_file)


# ---------- Subcommand: revise-wireframes (Agent 3 Mode 2) ----------


def cmd_revise_wireframes(args: argparse.Namespace) -> None:
    """Run Agent 3 only — revise an existing design brief with PM feedback.

    In this scaffolding pass, revision applies to the design brief
    document only; SVG wireframe regeneration lands in a follow-up
    prompt.
    """
    if not args.context_path and not args.context_text:
        print("Error: revise-wireframes requires at least one of --context-path or --context-text.")
        sys.exit(1)

    design_path = Path(args.design_brief_path).expanduser().resolve()
    if not design_path.exists() or not design_path.is_file():
        print(f"Error: Design brief file not found: {design_path}")
        sys.exit(1)

    # Vault read resolution: prefer vault copy if PM edited it there
    vault_cfg = get_vault_config()
    if vault_cfg:
        fm_pre = read_frontmatter(design_path)
        slug = fm_pre.get("product_slug") or re.sub(
            r"_v\d+\.\d+$", "", design_path.stem.replace("design_brief_", "")
        )
        vault_cfg.initiative = fm_pre.get("initiative", "")
        try:
            design_path = Path(
                resolve_artifact_path("design_brief", slug, vault_cfg, str(design_path))
            )
        except FileNotFoundError:
            pass

    context_path_str = ""
    if args.context_path:
        cp = Path(args.context_path).expanduser().resolve()
        if not cp.exists():
            print(f"Error: Context path not found: {cp}")
            sys.exit(1)
        context_path_str = str(cp)

    crew_inputs = {
        "design_brief_path": str(design_path),
        "context_path": context_path_str,
        "context_text": args.context_text or "",
    }

    print(f"\nRevising design brief: {design_path.name}\n")

    fm = read_frontmatter(design_path)
    label = fm.get("slug") or re.sub(
        r"_v\d+\.\d+$", "", design_path.stem.replace("design_brief_", "")
    )
    product_slug = fm.get("product_slug") or label.lower().replace("_", "-")

    vault_cfg_for_provider = get_vault_config()
    if vault_cfg_for_provider:
        vault_cfg_for_provider.initiative = fm.get("initiative", "")

    old_vault_file = ""
    if vault_cfg_for_provider:
        candidate = Path(str(design_path))
        if candidate.exists() and "PM Agent" in str(candidate):
            old_vault_file = str(candidate)

    def _on_approve(new_vault_path: str) -> None:
        if old_vault_file and old_vault_file != new_vault_path and Path(old_vault_file).exists():
            mark_superseded(old_vault_file, Path(new_vault_path).stem)

    provider, token = _install_checkpoint_provider(
        handlers=[
            ArtifactHandler(
                artifact_type="design_brief",
                pydantic_class=DesignBriefOutput,
                render_fn=lambda obj: render_design_brief_to_markdown(obj, slug=label),
                save_output_fn=lambda md, _obj: save_design_brief(md, label, "1.0"),
                version="1.0",
                upstream="prfaq",
                downstream="brd",
                post_approve=_on_approve,
            ),
        ],
        vault_cfg=vault_cfg_for_provider,
        product_slug=product_slug,
    )

    try:
        try:
            result = PmAgentSystem().revise_design_brief_crew().kickoff(inputs=crew_inputs)
        except Exception as e:
            print(f"\nError running crew: {e}")
            sys.exit(1)
    finally:
        reset_provider(token)

    brief = extract_pydantic_output(result, DesignBriefOutput)
    if brief is None:
        print("\nError: Agent 3 did not return a valid DesignBriefOutput.")
        sys.exit(1)

    record = provider.artifacts.get("design_brief")
    if record is None:
        markdown = render_design_brief_to_markdown(brief, slug=label)
        working_copy = save_design_brief(markdown, label, "1.0")
        if vault_cfg_for_provider:
            write_revision_to_vault(markdown, "design_brief", product_slug, vault_cfg_for_provider,
                                    upstream="prfaq", downstream="brd")
    else:
        working_copy = record.output_path
    print(f"\nRevision complete. Working copy saved to: {working_copy}")

    if vault_cfg_for_provider:
        generate_index_note(product_slug, vault_cfg_for_provider)


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


def cmd_feedback_status(args: argparse.Namespace) -> None:
    """Print a dashboard of feedback items in the inbox."""
    from pm_agent_system.feedback_inbox import load_all_feedback, get_inbox_dir
    from collections import Counter

    items = load_all_feedback()
    inbox = get_inbox_dir()

    if not items:
        print(f"Feedback inbox: {inbox}")
        print("  (empty)")
        print()
        print("To add a feedback item, create a markdown file in the inbox")
        print("directory with YAML frontmatter. See docs or the planning doc")
        print("'stakeholder_feedback_loop_plan' for the schema.")
        return

    # Apply status filter
    show = (getattr(args, "show", None) or "open").lower()
    if show == "all":
        visible = items
    else:
        visible = [it for it in items if it.status == show]

    # Counts across all items regardless of filter
    counts = Counter(it.status for it in items)

    print(f"Feedback inbox: {inbox}")
    print(f"  Open:         {counts.get('open', 0)}")
    print(f"  Incorporated: {counts.get('incorporated', 0)}")
    print(f"  Rejected:     {counts.get('rejected', 0)}")
    print(f"  Deferred:     {counts.get('deferred', 0)}")
    print()

    if not visible:
        print(f"No items with status='{show}' to display.")
        print(f"Use 'feedback status --show all' to see every item.")
        return

    print(f"Showing {len(visible)} item(s) with status='{show}':")
    print()

    # Optional artifact filter (only among visible items)
    artifact_filter = getattr(args, "artifact", None)
    if artifact_filter:
        visible = [
            it for it in visible
            if any(impact.artifact == artifact_filter for impact in it.affects)
        ]
        if not visible:
            print(f"  (no items affecting '{artifact_filter}')")
            return

    for it in visible:
        affects_display = (
            ", ".join(impact.artifact for impact in it.affects)
            if it.affects
            else "unclassified"
        )
        summary = it.summary or "(no summary)"
        if len(summary) > 60:
            summary = summary[:57] + "..."
        print(f"  {it.id}")
        print(f"    Source:  {it.source}")
        print(f"    Affects: {affects_display}")
        print(f"    Summary: {summary}")
        if it.contradictions:
            print(f"    Contradictions: {len(it.contradictions)}")
        if it.research_gaps:
            print(f"    Research gaps: {len(it.research_gaps)}")
        if it.status == "rejected" and it.rejection_reason:
            print(f"    Rejected: {it.rejection_reason}")
        if it.status == "deferred" and it.defer_until:
            print(f"    Deferred until: {it.defer_until}")
        print()


def cmd_feedback_classify(args: argparse.Namespace) -> None:
    """Run the feedback classifier on open items in the inbox.

    Reads each unclassified open item (or all open items if --rerun),
    invokes the classifier crew with artifact summaries and other
    feedback summaries, writes the classification back to the item's
    YAML frontmatter, and prints a routing table.
    """
    from pm_agent_system.feedback_inbox import (
        load_all_feedback,
        load_feedback_by_id,
        write_feedback_item,
    )
    from pm_agent_system.artifact_summary import read_all_summaries
    from pm_agent_system.models import FeedbackClassification

    # Resolve target items
    item_filter = getattr(args, "item", None)
    rerun = getattr(args, "rerun", False)
    if item_filter:
        item = load_feedback_by_id(item_filter)
        if item is None:
            print(f"Error: feedback item not found: {item_filter}")
            sys.exit(1)
        # TD4 fix: warn or abort on non-open items unless --rerun signals intent
        if item.status != "open":
            if not rerun:
                print(
                    f"Error: {item.id} has status '{item.status}', not 'open'. "
                    f"Use --rerun to classify anyway."
                )
                sys.exit(1)
            print(
                f"Warning: {item.id} has status '{item.status}'. "
                f"Reclassifying anyway (--rerun was set)."
            )
        targets = [item]
    else:
        all_items = load_all_feedback()
        targets = [it for it in all_items if it.status == "open"]

    if not targets:
        print("No open feedback items to classify.")
        return

    # Filter already-classified unless --rerun
    if not rerun:
        before = len(targets)
        targets = [it for it in targets if not it.affects]
        skipped = before - len(targets)
        if skipped and not targets:
            print(f"All {skipped} open item(s) are already classified.")
            print("Use --rerun to reclassify them.")
            return
        if skipped:
            print(f"Skipping {skipped} already-classified item(s). "
                  f"Use --rerun to include them.")

    print(f"\nClassifying {len(targets)} feedback item(s)...\n")

    # Pre-compute artifact summaries once (shared across all items)
    summaries = read_all_summaries()

    # Build "other feedback summaries" context once (used per-item with
    # the current item excluded at call time)
    all_open = load_all_feedback()
    all_open_by_id = {it.id: it for it in all_open if it.status == "open"}

    t_start = time.monotonic()

    for idx, item in enumerate(targets, 1):
        print(f"[{idx}/{len(targets)}] Classifying {item.id} from {item.source}...")

        # Build other-feedback context, excluding the current item
        other_lines = []
        for other_id, other in all_open_by_id.items():
            if other_id == item.id:
                continue
            other_summary = other.summary or "(no summary)"
            other_lines.append(f"- {other_id} ({other.source}): {other_summary}")
        other_feedback_summaries = (
            "\n".join(other_lines) if other_lines else "(none)"
        )

        crew_inputs = {
            "feedback_id": item.id,
            "feedback_source": item.source,
            "feedback_body": item.raw_text or "(no body provided)",
            "research_brief_summary": summaries.get("research_brief", "") or "(no research brief yet)",
            "prfaq_summary": summaries.get("prfaq", "") or "(no PRFAQ yet)",
            "design_brief_summary": summaries.get("design_brief", "") or "(no design brief yet)",
            "brd_summary": summaries.get("brd", "") or "(no BRD yet)",
            "build_spec_summary": summaries.get("build_spec", "") or "(no build spec yet)",
            "other_feedback_summaries": other_feedback_summaries,
        }

        t0 = time.monotonic()
        try:
            result = PmAgentSystem().feedback_classify_crew().kickoff(inputs=crew_inputs)
        except Exception as exc:
            print(f"  Error classifying {item.id}: {exc}")
            continue
        elapsed = time.monotonic() - t0

        classification = extract_pydantic_output(result, FeedbackClassification)
        if classification is None:
            print(f"  Classifier returned invalid output for {item.id}; skipping")
            continue

        # Copy classifier output back onto the item
        item.affects = classification.affects
        item.research_gaps = classification.research_gaps
        item.contradictions = classification.contradictions
        write_feedback_item(item)
        print(f"  Done in {elapsed:.1f}s")

    total_elapsed = time.monotonic() - t_start

    # Routing table
    # TD7 fix: use the in-memory `item` objects (already updated in the
    # loop above) instead of re-reading from disk per item.
    print("\nRouting summary:")
    print("-" * 70)
    for item in targets:
        if item.affects:
            artifacts = ", ".join(
                f"{imp.artifact} ({', '.join(imp.sections)})" if imp.sections else imp.artifact
                for imp in item.affects
            )
        else:
            artifacts = "(no artifacts affected)"
        print(f"  {item.id} ({item.source}):")
        print(f"    Affects: {artifacts}")
        if item.contradictions:
            print(f"    Contradictions: {len(item.contradictions)}")
            for flag in item.contradictions:
                print(f"      - {flag.summary} [conflicts with {flag.conflicts_with}]")
        if item.research_gaps:
            print(f"    Research gaps: {len(item.research_gaps)}")
            for gap in item.research_gaps:
                print(f"      - [{gap.tool}] {gap.query}")
    print("-" * 70)
    print(f"Total classify time: {total_elapsed:.1f}s")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pm_agent_system")
    sub = parser.add_subparsers(dest="command", required=True)

    p_research = sub.add_parser("research", help="Run Agent 1 only (research brief)")
    p_research.add_argument("input_file", help="Path to input brief (.md recommended; .yaml/.yml also accepted)")
    p_research.add_argument("--skip-validation", action="store_true", help="Skip the pre-research challenge questions")
    p_research.add_argument("--open", action="store_true", help="Open the HTML artifact in the default browser when done")
    p_research.set_defaults(func=cmd_research)

    p_generate = sub.add_parser(
        "generate", help="Run Agent 1 then Agent 2 to produce a PRFAQ v1.0"
    )
    p_generate.add_argument("input_file", help="Path to input brief (.md recommended; .yaml/.yml also accepted)")
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

    # ----- Agent 4 commands -----

    p_full = sub.add_parser(
        "full-pipeline",
        help="Run all agents end-to-end (research → PRFAQ → design brief → BRD → build spec)",
    )
    p_full.add_argument("input_file", help="Path to input brief (.md recommended; .yaml/.yml also accepted)")
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
    p_full.add_argument(
        "--skip-design",
        action="store_true",
        help="Skip Agent 3 (design brief) and run the three-agent pipeline as before",
    )
    p_full.add_argument("--open", action="store_true", help="Open the final HTML artifact in the default browser when done")
    p_full.set_defaults(func=cmd_full_pipeline)

    p_brd = sub.add_parser(
        "brd",
        help="Run Agent 4 only — generate BRD + build spec from an approved PRFAQ",
    )
    p_brd.add_argument("input_file", help="Path to original input brief (.md or .yaml/.yml) for context")
    p_brd.add_argument("--prfaq-path", required=True, help="Path to approved PRFAQ markdown")
    p_brd.add_argument("--research-path", help="Optional path to research brief markdown")
    p_brd.add_argument(
        "--design-brief-path",
        help="Optional path to approved design brief markdown (Agent 3 output)",
    )
    p_brd.add_argument(
        "--requirements-path",
        help="Optional path to customer requirements file (CSV, Excel, Markdown, or Word)",
    )
    p_brd.add_argument("--target-tool", choices=VALID_TARGET_TOOLS)
    p_brd.add_argument("--open", action="store_true", help="Open the HTML artifact in the default browser when done")
    p_brd.set_defaults(func=cmd_brd)

    p_spec = sub.add_parser(
        "build-spec",
        help="Run Agent 4 only — regenerate build spec from an approved BRD",
    )
    p_spec.add_argument("--brd-path", required=True, help="Path to approved BRD markdown")
    p_spec.add_argument("--target-tool", choices=VALID_TARGET_TOOLS)
    p_spec.set_defaults(func=cmd_build_spec)

    p_rbrd = sub.add_parser(
        "revise-brd",
        help="Run Agent 4 only — revise an existing BRD",
    )
    p_rbrd.add_argument("--brd-path", required=True, help="Path to current BRD markdown")
    p_rbrd.add_argument("--context-path", help="File or folder with revision context")
    p_rbrd.add_argument("--context-text", help="Inline revision instructions")
    p_rbrd.set_defaults(func=cmd_revise_brd)

    # ----- Agent 3 commands -----

    p_wire = sub.add_parser(
        "wireframes",
        help="Run Agent 3 only — generate a design brief from an approved PRFAQ",
    )
    p_wire.add_argument("input_file", help="Path to original input brief (.md or .yaml/.yml) for context")
    p_wire.add_argument("--prfaq-path", required=True, help="Path to approved PRFAQ markdown")
    p_wire.add_argument("--research-path", help="Optional path to research brief markdown")
    p_wire.set_defaults(func=cmd_wireframes)

    p_rwire = sub.add_parser(
        "revise-wireframes",
        help="Run Agent 3 only — revise an existing design brief",
    )
    p_rwire.add_argument("--design-brief-path", required=True, help="Path to current design brief markdown")
    p_rwire.add_argument("--context-path", help="File or folder with revision context")
    p_rwire.add_argument("--context-text", help="Inline revision instructions")
    p_rwire.set_defaults(func=cmd_revise_wireframes)

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

    # ----- Feedback inbox (Wave 1: status only; classify/apply land in Wave 2) -----

    p_feedback = sub.add_parser(
        "feedback",
        help="Manage the stakeholder feedback inbox (output/feedback/)",
    )
    feedback_sub = p_feedback.add_subparsers(dest="feedback_command", required=True)

    p_fb_status = feedback_sub.add_parser(
        "status",
        help="Show the feedback inbox dashboard",
    )
    p_fb_status.add_argument(
        "--show",
        choices=["open", "incorporated", "rejected", "deferred", "all"],
        default="open",
        help="Which items to display (default: open)",
    )
    p_fb_status.add_argument(
        "--artifact",
        choices=["research_brief", "prfaq", "design_brief", "brd", "build_spec"],
        help="Only show items affecting this artifact",
    )
    p_fb_status.set_defaults(func=cmd_feedback_status)

    p_fb_classify = feedback_sub.add_parser(
        "classify",
        help="Route each open feedback item to the artifacts it affects",
    )
    p_fb_classify.add_argument(
        "--item",
        help="Only classify a single feedback item by ID (e.g. fb-2026-04-24-001)",
    )
    p_fb_classify.add_argument(
        "--rerun",
        action="store_true",
        help="Reclassify items that already have an 'affects' list populated",
    )
    p_fb_classify.set_defaults(func=cmd_feedback_classify)

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
        data = parse_input(str(example_path))
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
