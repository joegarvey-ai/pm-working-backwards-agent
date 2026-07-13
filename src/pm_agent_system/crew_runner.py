"""Shared crew-run helpers: build-spec render hook, artifact recording, callbacks.

Extracted from ``main.py`` (audit item #16). Three command handlers
(``cmd_full_pipeline`` full run, ``cmd_full_pipeline`` Agent-4 resume, and
``cmd_brd``) all needed the same two pieces of wiring:

1. A build-spec render function that appends the deterministic STRIDE stub and
   RACI matrix to the spec from the live ``BRDOutput`` before the provider
   writes it. This was duplicated byte-for-byte in two handlers.
2. A task-callback that stashes the ``BRDOutput`` (so the render hook can see
   it), records absolute per-task timings, and updates the resume checkpoint.

Factoring these into parameterized factories removes the duplication while
keeping behavior identical: each factory closes over exactly the state the
inline version did.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from pm_agent_system.checkpoint import record_artifact, save_checkpoint
from pm_agent_system.io_layer import (
    save_brd,
    save_brd_exports,
    save_design_brief,
    save_markdown_brief,
    save_prfaq,
)
from pm_agent_system.models import (
    BRDOutput,
    CodingPromptOutput,
    DesignBriefOutput,
    PRFAQOutput,
    ResearchOutput,
)
from pm_agent_system.utils import (
    render_brd_to_markdown,
    render_design_brief_to_markdown,
    render_prfaq_to_markdown,
    render_research_to_markdown,
)
from pm_agent_system.vault import write_to_vault
from pm_agent_system.versioning import _brd_version_from_output, _prfaq_version_from_output

logger = logging.getLogger(__name__)

# Maps Pydantic output classes to their artifact_type label, used by the few
# post-kickoff hooks that need to know which artifact a TaskOutput corresponds to.
_PYDANTIC_TO_ARTIFACT: dict[type, str] = {
    ResearchOutput: "research_brief",
    PRFAQOutput: "prfaq",
    DesignBriefOutput: "design_brief",
    BRDOutput: "brd",
    CodingPromptOutput: "build_spec",
}


def make_build_spec_render(
    original_render_fn: Callable, brd_holder: dict
) -> Callable:
    """Wrap a build-spec render fn so it augments the spec with STRIDE + RACI.

    ``brd_holder`` is a mutable one-key dict populated by the task callback once
    the BRD task completes. When present, the deterministic STRIDE stub and RACI
    matrix are appended to the CodingPromptOutput before rendering.
    """

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


def record_artifact_from_task_output(
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


def make_pipeline_task_callback(
    *,
    brd_holder: dict,
    task_timings: dict,
    t0: float,
    label,
    slug,
    output_dir,
    checkpoint,
    provider,
    vault_cfg,
    product_slug,
) -> Callable:
    """Build the full-pipeline task callback.

    Stashes the BRDOutput for the render hook, records absolute per-task
    completion times relative to the pipeline start (``t0``), and records the
    artifact into the resume checkpoint. Call this after ``t0`` and
    ``task_timings`` exist, just before assigning ``crew.task_callback``.
    """

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
        # Absolute completion time from pipeline start. Under async execution,
        # tasks complete out of order, so absolute timestamps show overlap.
        task_timings[task_name] = now - t0
        record_artifact_from_task_output(
            task_output, label, slug, output_dir, checkpoint, provider,
            vault_config=vault_cfg, product_slug=product_slug,
        )

    return _task_callback
