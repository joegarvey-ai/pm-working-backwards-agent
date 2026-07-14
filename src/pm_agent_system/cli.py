"""Argparse command-line interface definition.

Extracted from ``main.py`` (audit item #16). Builds the argument parser and
wires each subcommand to its ``cmd_*`` handler in ``main``. Kept separate so
the 200-line parser spec does not crowd the command implementations.

Import note: this module imports the handlers from ``main`` at load time.
``main`` imports ``build_parser`` lazily (inside ``run()``), so ``main`` is
always fully initialized before this module is imported — no import cycle.
"""

from __future__ import annotations

import argparse

from pm_agent_system.main import (
    cmd_brd,
    cmd_build_spec,
    cmd_clean,
    cmd_diff,
    cmd_feedback_classify,
    cmd_feedback_status,
    cmd_full_pipeline,
    cmd_generate,
    cmd_ingest_feedback,
    cmd_publish_doc,
    cmd_research,
    cmd_revise,
    cmd_revise_brd,
    cmd_revise_wireframes,
    cmd_seed_taskei,
    cmd_view,
    cmd_wireframes,
)
from pm_agent_system.models import VALID_TARGET_TOOLS


def build_parser() -> argparse.ArgumentParser:
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
    p_generate.add_argument("--research-path", help="Path to an existing research brief markdown. When set, reuse it and skip Agent 1.")
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
    p_revise.add_argument("--open", action="store_true", help="Open the HTML artifact in the default browser when done")
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
    p_full.add_argument(
        "--sequential-brd",
        action="store_true",
        help="Run the BRD structure/cost/compliance steps sequentially instead of in parallel. Slower but avoids the Bedrock toolResult race. Auto-enabled when LLM_PROVIDER=bedrock.",
    )
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
    p_brd.add_argument(
        "--sequential-brd",
        action="store_true",
        help="Run the BRD structure/cost/compliance steps sequentially instead of in parallel. Slower but avoids the Bedrock toolResult race. Auto-enabled when LLM_PROVIDER=bedrock.",
    )
    p_brd.add_argument(
        "--verify",
        action="store_true",
        help="Run the advisory verification gate on the PRFAQ before generating the BRD (style, consistency, sourcing, grounding). Warns; does not hard-block.",
    )
    p_brd.set_defaults(func=cmd_brd)

    p_spec = sub.add_parser(
        "build-spec",
        help="Run Agent 4 only — regenerate build spec from an approved BRD",
    )
    p_spec.add_argument("--brd-path", required=True, help="Path to approved BRD markdown")
    p_spec.add_argument("--target-tool", choices=VALID_TARGET_TOOLS)
    p_spec.add_argument("--open", action="store_true", help="Open the HTML artifact in the default browser when done")
    p_spec.set_defaults(func=cmd_build_spec)

    p_rbrd = sub.add_parser(
        "revise-brd",
        help="Run Agent 4 only — revise an existing BRD",
    )
    p_rbrd.add_argument("--brd-path", required=True, help="Path to current BRD markdown")
    p_rbrd.add_argument("--context-path", help="File or folder with revision context")
    p_rbrd.add_argument("--context-text", help="Inline revision instructions")
    p_rbrd.add_argument("--open", action="store_true", help="Open the HTML artifact in the default browser when done")
    p_rbrd.set_defaults(func=cmd_revise_brd)

    # ----- Agent 3 commands -----

    p_wire = sub.add_parser(
        "wireframes",
        help="Run Agent 3 only — generate a design brief from an approved PRFAQ",
    )
    p_wire.add_argument("input_file", help="Path to original input brief (.md or .yaml/.yml) for context")
    p_wire.add_argument("--prfaq-path", required=True, help="Path to approved PRFAQ markdown")
    p_wire.add_argument("--research-path", help="Optional path to research brief markdown")
    p_wire.add_argument("--open", action="store_true", help="Open the HTML artifact in the default browser when done")
    p_wire.set_defaults(func=cmd_wireframes)

    p_rwire = sub.add_parser(
        "revise-wireframes",
        help="Run Agent 3 only — revise an existing design brief",
    )
    p_rwire.add_argument("--design-brief-path", required=True, help="Path to current design brief markdown")
    p_rwire.add_argument("--context-path", help="File or folder with revision context")
    p_rwire.add_argument("--context-text", help="Inline revision instructions")
    p_rwire.add_argument("--open", action="store_true", help="Open the HTML artifact in the default browser when done")
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

    # ----- Gated write-back integrations (audit #19) -----
    # The ONLY commands that write outside output/. Each requires the
    # builder-mcp / slack-mcp binary + a live Midway session, and each writes
    # only after an explicit interactive confirmation (default No).

    p_publish = sub.add_parser(
        "publish-doc",
        help="Publish an approved artifact markdown to a document store (writes externally; confirms first)",
        description=(
            "Publish an approved artifact (PRFAQ/BRD/etc.) markdown file to a "
            "document store. Shows a preview and requires an explicit "
            "confirmation before writing. Targets: 'quip' and 'pippin' ride the "
            "builder-mcp / python-pippin-mcp binaries (Midway auth); "
            "'sharepoint' rides the separate sharepoint-mcp binary (FedAuth "
            "cookie auth). Each requires its binary on PATH and a live "
            "Midway/FedAuth session. Amazon is migrating off Quip toward "
            "SharePoint; Pippin is the canonical PRFAQ/BRD platform and needs "
            "an explicit --pippin-project."
        ),
    )
    p_publish.add_argument("--artifact-path", required=True, help="Path to the approved artifact markdown to publish")
    p_publish.add_argument(
        "--target",
        default="quip",
        help="Document store to publish to (default: quip). One of: quip, sharepoint, pippin.",
    )
    p_publish.add_argument(
        "--folder",
        default="",
        help=(
            "Optional destination. Quip: comma-separated folder/user member IDs. "
            "SharePoint: site/library/folder path. (Pippin uses --pippin-project "
            "instead.)"
        ),
    )
    p_publish.add_argument(
        "--pippin-project",
        default="",
        help=(
            "Pippin project ID to create the artifact in (required for "
            "--target pippin; falls back to PIPPIN_PROJECT_ID). No default."
        ),
    )
    p_publish.set_defaults(func=cmd_publish_doc)

    p_seed = sub.add_parser(
        "seed-taskei",
        help="Create one Taskei task per BRD functional requirement, under a parent EPIC (writes externally; confirms first)",
        description=(
            "Parse the functional requirements from an approved BRD markdown "
            "file and create one Taskei task per requirement, nested under a "
            "parent EPIC. Prints the full plan first; --dry-run stops there. "
            "Requires --taskei-room (or TASKEI_ROOM_ID), the builder-mcp "
            "binary, and a live Midway session."
        ),
    )
    p_seed.add_argument("--brd-path", required=True, help="Path to the approved BRD markdown")
    p_seed.add_argument(
        "--taskei-room",
        default="",
        help="Taskei room UUID to create tasks in (required; falls back to TASKEI_ROOM_ID). No default.",
    )
    p_seed.add_argument(
        "--parent-task",
        default="",
        help="Optional existing task ID to nest the FR tasks under. When set, no EPIC is created.",
    )
    p_seed.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the tasks that would be created without writing anything.",
    )
    p_seed.set_defaults(func=cmd_seed_taskei)

    p_ingest = sub.add_parser(
        "ingest-feedback",
        help="Ingest stakeholder feedback from Slack into the local feedback inbox",
        description=(
            "Pull messages from a Slack channel and write each as a feedback "
            "item (status=open) into output/feedback/. This writes locally, "
            "not to an external system. Requires the slack-mcp binary and a "
            "live Midway session. Run 'feedback classify' afterward to route "
            "the ingested items."
        ),
    )
    p_ingest.add_argument(
        "--source",
        default="slack",
        choices=["slack"],
        help="Feedback source (v1: slack only).",
    )
    p_ingest.add_argument("--channel", default="", help="Slack channel name or ID to pull messages from")
    p_ingest.add_argument("--since", default="", help="Optional ISO-8601 start date (e.g. 2026-07-01)")
    p_ingest.set_defaults(func=cmd_ingest_feedback)

    return parser
