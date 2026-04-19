"""Per-agent checkpoint manifest for the full pipeline.

Persists completed agent outputs to a flat JSON manifest so that
``full-pipeline --resume`` can skip already-completed agents after a
crash, avoiding re-paying for their API calls.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

CHECKPOINT_FILENAME = ".checkpoint.json"


def compute_input_hash(input_path: str) -> str:
    """SHA-256 hash of the normalized input brief.

    Works for both YAML (.yaml/.yml) and Obsidian-style markdown (.md):
    parses through the unified input parser and re-dumps the resulting dict
    with sorted keys so cosmetic edits and format swaps that produce the
    same semantic content don't bust the resume cache.
    """
    from pm_agent_system.input_parser import parse_input

    data = parse_input(input_path) or {}
    normalized = yaml.dump(data, sort_keys=True, default_flow_style=False).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _checkpoint_path(output_dir: Path) -> Path:
    return output_dir / CHECKPOINT_FILENAME


def load_checkpoint(output_dir: Path) -> dict | None:
    """Load an existing checkpoint manifest, or return None."""
    path = _checkpoint_path(output_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_checkpoint(output_dir: Path, checkpoint: dict) -> None:
    """Write the checkpoint manifest to disk."""
    path = _checkpoint_path(output_dir)
    path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")


def delete_checkpoint(output_dir: Path) -> None:
    """Remove the checkpoint manifest after successful completion."""
    path = _checkpoint_path(output_dir)
    if path.exists():
        path.unlink()


def new_checkpoint(input_hash: str, model: str) -> dict:
    """Create a fresh checkpoint manifest."""
    return {
        "input_hash": input_hash,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "artifacts": {},
    }


def record_artifact(
    checkpoint: dict,
    artifact_name: str,
    file_path: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    estimated_cost_usd: float = 0.0,
) -> None:
    """Add or update an artifact entry in the checkpoint."""
    checkpoint["artifacts"][artifact_name] = {
        "path": file_path,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "estimated_cost_usd": estimated_cost_usd,
    }


def completed_stages(checkpoint: dict | None) -> set[str]:
    """Return the set of artifact names that are completed and still on disk."""
    if checkpoint is None:
        return set()
    done = set()
    for name, info in checkpoint.get("artifacts", {}).items():
        if Path(info["path"]).exists():
            done.add(name)
    return done
