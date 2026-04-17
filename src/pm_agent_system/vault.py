"""Obsidian vault integration for pipeline artifacts.

Writes artifacts to the PM's Obsidian vault with YAML frontmatter,
wikilinks connecting the artifact chain, version history, and
divergence detection. The vault copy is the PM's working document;
output/ remains the system record.

All vault operations are optional and non-blocking. If OBSIDIAN_VAULT_PATH
is not set, vault integration is silently disabled.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Maps artifact_type keys to human-readable display names.
ARTIFACT_DISPLAY_NAMES: dict[str, str] = {
    "research_brief": "Research Brief",
    "prfaq": "PRFAQ",
    "brd": "BRD",
    "build_spec": "Build Spec",
}

# Maps artifact_type to the agent responsible for generating it.
ARTIFACT_AGENTS: dict[str, str] = {
    "research_brief": "Research Agent",
    "prfaq": "PRFAQ Agent",
    "brd": "BRD Agent",
    "build_spec": "Build Spec Agent",
}

# Ordered artifact chain for traceability links.
ARTIFACT_CHAIN = ["research_brief", "prfaq", "brd", "build_spec"]


# ---------- Data classes ----------


@dataclass
class VaultConfig:
    vault_path: str
    folder_prefix: str  # default "PM Agent"


@dataclass
class DivergenceResult:
    diverged: bool
    generated_at: str | None
    file_modified_at: str | None
    vault_path: str
    output_path: str


# ---------- Configuration ----------


def get_vault_config() -> VaultConfig | None:
    """Read vault configuration from environment.

    Returns None if OBSIDIAN_VAULT_PATH is not set (vault integration
    silently disabled). Validates the path exists and is a directory.
    """
    vault_path = os.getenv("OBSIDIAN_VAULT_PATH", "").strip()
    if not vault_path:
        return None

    vault_path = str(Path(vault_path).expanduser().resolve())
    if not Path(vault_path).is_dir():
        logger.warning(
            "OBSIDIAN_VAULT_PATH is set to '%s' but the directory does not exist. "
            "Vault integration disabled.",
            vault_path,
        )
        return None

    folder_prefix = os.getenv("OBSIDIAN_FOLDER_PREFIX", "PM Agent").strip()
    return VaultConfig(vault_path=vault_path, folder_prefix=folder_prefix)


# ---------- Hashing ----------


_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


def compute_body_hash(markdown_content: str) -> str:
    """SHA-256 hash of the document body (everything below YAML frontmatter).

    If no frontmatter exists, hashes the entire content. This ensures that
    frontmatter-only edits (e.g. changing status from draft to approved)
    do NOT register as divergence.
    """
    body = _FRONTMATTER_RE.sub("", markdown_content, count=1)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# ---------- Frontmatter ----------


def build_frontmatter(
    artifact_type: str,
    product_slug: str,
    version: str,
    body_hash: str,
    upstream: str | None,
    downstream: str | None,
) -> dict:
    """Construct the YAML frontmatter dict for a vault artifact."""
    display_name = ARTIFACT_DISPLAY_NAMES.get(artifact_type, artifact_type)
    agent_name = ARTIFACT_AGENTS.get(artifact_type, "Unknown Agent")

    fm: dict = {
        "title": f"{product_slug} — {display_name}",
        "artifact_type": artifact_type,
        "product_slug": product_slug,
        "version": version,
        "status": "draft",
        "pipeline_run": datetime.now(timezone.utc).isoformat(),
        "agent": agent_name,
        "original_hash": body_hash,
        "tags": ["pm-agent", product_slug, artifact_type],
        "aliases": [f"{product_slug} {display_name}"],
    }

    if upstream:
        fm["upstream"] = f"[[{upstream}]]"
    if downstream:
        fm["downstream"] = f"[[{downstream}]]"

    return fm


def inject_frontmatter(markdown_content: str, frontmatter: dict) -> str:
    """Serialize frontmatter as YAML and prepend to the markdown content.

    If the content already has frontmatter (starts with ``---``), replaces it.
    """
    fm_str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False, allow_unicode=True)
    fm_block = f"---\n{fm_str}---\n"

    # Replace existing frontmatter if present.
    if markdown_content.startswith("---"):
        match = _FRONTMATTER_RE.match(markdown_content)
        if match:
            return fm_block + markdown_content[match.end():]

    return fm_block + markdown_content


# ---------- Traceability ----------


def _artifact_filename(artifact_type: str, version: str | None = None) -> str:
    """Generate the vault filename (without extension) for an artifact."""
    if version:
        return f"{artifact_type}_v{version}"
    return artifact_type


def inject_traceability_section(
    markdown_content: str,
    artifact_type: str,
    upstream_file: str | None,
    downstream_file: str | None,
) -> str:
    """Insert a one-line traceability callout after frontmatter, before the first heading.

    Shows the artifact chain with the current artifact bolded.
    """
    chain_parts: list[str] = []
    for at in ARTIFACT_CHAIN:
        if at == artifact_type:
            chain_parts.append(f"**{ARTIFACT_DISPLAY_NAMES.get(at, at)}**")
        elif at == _prev_artifact(artifact_type) and upstream_file:
            chain_parts.append(f"[[{upstream_file}|{ARTIFACT_DISPLAY_NAMES.get(at, at)}]]")
        elif at == _next_artifact(artifact_type) and downstream_file:
            chain_parts.append(f"[[{downstream_file}|{ARTIFACT_DISPLAY_NAMES.get(at, at)}]]")
        else:
            # Only include if it's between existing chain nodes
            chain_parts.append(ARTIFACT_DISPLAY_NAMES.get(at, at))

    chain_line = f"> **Artifact chain:** {' \u2192 '.join(chain_parts)}\n\n"

    # Insert after frontmatter, before the first heading
    if markdown_content.startswith("---"):
        match = _FRONTMATTER_RE.match(markdown_content)
        if match:
            after_fm = markdown_content[match.end():]
            return markdown_content[: match.end()] + chain_line + after_fm

    return chain_line + markdown_content


def _prev_artifact(artifact_type: str) -> str | None:
    idx = ARTIFACT_CHAIN.index(artifact_type) if artifact_type in ARTIFACT_CHAIN else -1
    return ARTIFACT_CHAIN[idx - 1] if idx > 0 else None


def _next_artifact(artifact_type: str) -> str | None:
    idx = ARTIFACT_CHAIN.index(artifact_type) if artifact_type in ARTIFACT_CHAIN else -1
    return ARTIFACT_CHAIN[idx + 1] if 0 <= idx < len(ARTIFACT_CHAIN) - 1 else None


# ---------- Divergence detection ----------


def detect_divergence(vault_file_path: str, output_path: str = "") -> DivergenceResult:
    """Check whether the vault copy has been modified since it was generated.

    Compares the stored ``original_hash`` in frontmatter against the
    current body hash. Frontmatter-only changes (e.g. status edits)
    do NOT trigger divergence.
    """
    vp = Path(vault_file_path)
    if not vp.exists():
        return DivergenceResult(
            diverged=False,
            generated_at=None,
            file_modified_at=None,
            vault_path=vault_file_path,
            output_path=output_path,
        )

    content = vp.read_text(encoding="utf-8")
    current_hash = compute_body_hash(content)

    # Extract original_hash from frontmatter
    fm_match = _FRONTMATTER_RE.match(content)
    original_hash = None
    generated_at = None
    if fm_match:
        try:
            fm_data = yaml.safe_load(fm_match.group()) or {}
            # yaml.safe_load on "---\n...\n---\n" returns the inner dict
            if isinstance(fm_data, str):
                fm_data = yaml.safe_load(content.split("---\n")[1]) or {}
            original_hash = fm_data.get("original_hash")
            generated_at = fm_data.get("pipeline_run")
        except yaml.YAMLError:
            pass

    if original_hash is None:
        # No hash stored — can't detect divergence, assume clean
        return DivergenceResult(
            diverged=False,
            generated_at=generated_at,
            file_modified_at=None,
            vault_path=vault_file_path,
            output_path=output_path,
        )

    mtime = datetime.fromtimestamp(vp.stat().st_mtime, tz=timezone.utc).isoformat()

    return DivergenceResult(
        diverged=(current_hash != original_hash),
        generated_at=generated_at,
        file_modified_at=mtime,
        vault_path=vault_file_path,
        output_path=output_path,
    )


def prompt_vault_or_output(artifact_name: str, divergence: DivergenceResult) -> bool:
    """Prompt the PM when the vault copy has diverged from the generated version.

    Returns True to use vault, False to use output/.
    If not diverged, returns True silently.
    """
    if not divergence.diverged:
        return True

    print(
        f"\nVault copy of {artifact_name} has been modified since it was generated.\n"
        f"\n"
        f"  Generated:   {divergence.generated_at or 'unknown'}\n"
        f"  Last edited: {divergence.file_modified_at or 'unknown'} (vault version)\n"
        f"\n"
        f"Use the vault version? (y/n)"
    )
    response = input("> ").strip().lower()
    return response in ("y", "yes")


# ---------- Artifact path resolution ----------


def resolve_artifact_path(
    artifact_type: str,
    product_slug: str,
    vault_config: VaultConfig | None,
    output_path: str,
) -> str:
    """Resolve which path to read an existing artifact from.

    Priority:
    1. If vault is configured and vault copy exists → check divergence, prompt if needed
    2. If vault not configured or vault copy missing → use output/ path
    3. If neither exists → raise an error
    """
    output_exists = output_path and Path(output_path).exists()

    if vault_config:
        vault_file = _vault_artifact_path(artifact_type, product_slug, vault_config)
        if vault_file.exists():
            divergence = detect_divergence(str(vault_file), output_path)
            display_name = ARTIFACT_DISPLAY_NAMES.get(artifact_type, artifact_type)
            use_vault = prompt_vault_or_output(display_name, divergence)
            if use_vault:
                return str(vault_file)
            elif output_exists:
                return output_path
            else:
                # Vault exists but user declined and output is gone — use vault anyway
                return str(vault_file)

    if output_exists:
        return output_path

    display_name = ARTIFACT_DISPLAY_NAMES.get(artifact_type, artifact_type)
    raise FileNotFoundError(
        f"{display_name} not found. Run the relevant agent first to generate it."
    )


def _vault_artifact_path(
    artifact_type: str,
    product_slug: str,
    vault_config: VaultConfig,
    version: str | None = None,
) -> Path:
    """Compute the expected vault path for an artifact.

    If version is given, looks for the exact version file.
    Otherwise, finds the latest version file for the artifact type.
    """
    folder = Path(vault_config.vault_path) / vault_config.folder_prefix / product_slug

    if version:
        return folder / f"{artifact_type}_v{version}.md"

    # Find the latest version
    if folder.exists():
        pattern = f"{artifact_type}_v*.md"
        matches = sorted(folder.glob(pattern))
        if matches:
            return matches[-1]

    # Default path for first version
    return folder / f"{artifact_type}_v1.0.md"


# ---------- Product slug ----------


def get_product_slug(input_config: dict) -> str:
    """Extract a filesystem-safe slug from the input YAML.

    Uses the feature_summary field, lowercased, with spaces replaced by
    hyphens and special characters removed.
    """
    name = input_config.get("feature_summary", "unknown")
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:50] if slug else "unknown"


# ---------- Core write ----------


def write_to_vault(
    markdown_content: str,
    artifact_type: str,
    product_slug: str,
    version: str,
    vault_config: VaultConfig,
    upstream: str | None = None,
    downstream: str | None = None,
) -> str:
    """Write an artifact to the Obsidian vault with frontmatter and traceability.

    Creates the folder structure, injects frontmatter and traceability
    section, and writes the file. Returns the vault file path.

    Never raises — logs a warning and returns empty string on failure.
    """
    try:
        body_hash = compute_body_hash(markdown_content)

        # Build upstream/downstream filenames for wikilinks
        upstream_file = _artifact_filename(upstream, version=None) if upstream else None
        downstream_file = _artifact_filename(downstream, version=None) if downstream else None

        fm = build_frontmatter(
            artifact_type=artifact_type,
            product_slug=product_slug,
            version=version,
            body_hash=body_hash,
            upstream=upstream_file,
            downstream=downstream_file,
        )

        content = inject_frontmatter(markdown_content, fm)
        content = inject_traceability_section(
            content,
            artifact_type,
            upstream_file,
            downstream_file,
        )

        # Create vault folder
        folder = Path(vault_config.vault_path) / vault_config.folder_prefix / product_slug
        folder.mkdir(parents=True, exist_ok=True)

        # Write the file
        filename = f"{artifact_type}_v{version}.md"
        vault_file = folder / filename
        vault_file.write_text(content, encoding="utf-8")

        logger.info("Vault artifact written: %s", vault_file)
        print(f"  Vault copy: {vault_file}")
        return str(vault_file)

    except Exception as exc:
        logger.warning("Failed to write vault artifact (%s): %s", artifact_type, exc)
        return ""
