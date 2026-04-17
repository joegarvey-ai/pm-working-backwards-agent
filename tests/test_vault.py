"""Tests for the Obsidian vault integration module."""

import os
from pathlib import Path

import pytest
import yaml

from unittest.mock import patch

from pm_agent_system.vault import (
    VaultConfig,
    build_frontmatter,
    compute_body_hash,
    detect_divergence,
    generate_all_products_note,
    generate_index_note,
    get_next_version,
    get_product_slug,
    get_vault_config,
    inject_frontmatter,
    inject_traceability_section,
    mark_superseded,
    resolve_artifact_path,
    strip_frontmatter,
    write_to_vault,
)


# ---------- compute_body_hash ----------


def test_compute_body_hash_same_content():
    """Same content produces the same hash."""
    content = "# Hello\n\nSome content here."
    assert compute_body_hash(content) == compute_body_hash(content)


def test_compute_body_hash_different_content():
    """Different content produces different hashes."""
    assert compute_body_hash("# A") != compute_body_hash("# B")


def test_compute_body_hash_ignores_frontmatter():
    """Content with frontmatter only hashes the body, not the frontmatter."""
    body = "# Hello\n\nSome content."
    with_fm = f"---\ntitle: Test\nstatus: draft\n---\n{body}"
    without_fm = body
    # The body hash should be the same (both hash just the body text)
    assert compute_body_hash(with_fm) == compute_body_hash(without_fm)


# ---------- build_frontmatter ----------


def test_build_frontmatter_all_fields_present():
    fm = build_frontmatter(
        artifact_type="prfaq",
        product_slug="analytics-dashboard",
        version="1.0",
        body_hash="abc123",
        upstream="research_brief",
        downstream="brd",
    )
    assert fm["title"] == "analytics-dashboard — PRFAQ"
    assert fm["artifact_type"] == "prfaq"
    assert fm["product_slug"] == "analytics-dashboard"
    assert fm["version"] == "1.0"
    assert fm["status"] == "draft"
    assert fm["original_hash"] == "abc123"
    assert fm["agent"] == "PRFAQ Agent"
    assert "pm-agent" in fm["tags"]
    assert "prfaq" in fm["tags"]
    assert fm["upstream"] == "[[research_brief]]"
    assert fm["downstream"] == "[[brd]]"
    assert "pipeline_run" in fm
    assert "aliases" in fm


def test_build_frontmatter_no_upstream_downstream():
    fm = build_frontmatter(
        artifact_type="research_brief",
        product_slug="test",
        version="1.0",
        body_hash="xyz",
        upstream=None,
        downstream=None,
    )
    assert "upstream" not in fm
    assert "downstream" not in fm


def test_build_frontmatter_with_initiative():
    fm = build_frontmatter(
        artifact_type="brd",
        product_slug="test",
        version="1.0",
        body_hash="xyz",
        upstream=None,
        downstream=None,
        initiative="commerce-platform",
    )
    assert fm["initiative"] == "commerce-platform"
    assert "commerce-platform" in fm["tags"]


# ---------- inject_frontmatter ----------


def test_inject_frontmatter_no_existing():
    content = "# Hello\n\nBody text."
    result = inject_frontmatter(content, {"title": "Test"})
    assert result.startswith("---\n")
    assert "title: Test" in result
    assert result.endswith("# Hello\n\nBody text.")


def test_inject_frontmatter_replaces_existing():
    content = "---\ntitle: Old\n---\n# Hello\n\nBody text."
    result = inject_frontmatter(content, {"title": "New"})
    assert "title: New" in result
    assert "title: Old" not in result
    assert "# Hello\n\nBody text." in result


# ---------- inject_traceability_section ----------


def test_inject_traceability_section():
    content = "---\ntitle: Test\n---\n# Hello\n\nBody."
    result = inject_traceability_section(content, "prfaq", "research_brief", "brd")
    assert "**Artifact chain:**" in result
    assert "**PRFAQ**" in result
    assert "[[research_brief|Research Brief]]" in result
    assert "[[brd|BRD]]" in result


# ---------- detect_divergence ----------


def test_detect_divergence_no_change(tmp_path):
    """Write a file and immediately check — no divergence."""
    body = "# Test\n\nOriginal content."
    body_hash = compute_body_hash(body)
    fm = {"original_hash": body_hash, "pipeline_run": "2026-01-01T00:00:00"}
    fm_str = yaml.dump(fm, default_flow_style=False)
    content = f"---\n{fm_str}---\n{body}"

    vault_file = tmp_path / "test.md"
    vault_file.write_text(content, encoding="utf-8")

    result = detect_divergence(str(vault_file))
    assert result.diverged is False


def test_detect_divergence_body_changed(tmp_path):
    """Write a file, modify the body, check — divergence detected."""
    original_body = "# Test\n\nOriginal content."
    body_hash = compute_body_hash(original_body)
    fm = {"original_hash": body_hash, "pipeline_run": "2026-01-01T00:00:00"}
    fm_str = yaml.dump(fm, default_flow_style=False)

    # Write original
    vault_file = tmp_path / "test.md"
    vault_file.write_text(f"---\n{fm_str}---\n{original_body}", encoding="utf-8")

    # Modify the body (keeping frontmatter intact)
    modified_content = f"---\n{fm_str}---\n# Test\n\nModified content."
    vault_file.write_text(modified_content, encoding="utf-8")

    result = detect_divergence(str(vault_file))
    assert result.diverged is True


def test_detect_divergence_frontmatter_only_change(tmp_path):
    """Changing only frontmatter (e.g. status) must NOT trigger divergence."""
    body = "# Test\n\nOriginal content."
    body_hash = compute_body_hash(body)
    fm = {"original_hash": body_hash, "pipeline_run": "2026-01-01T00:00:00", "status": "draft"}
    fm_str = yaml.dump(fm, default_flow_style=False)

    vault_file = tmp_path / "test.md"
    vault_file.write_text(f"---\n{fm_str}---\n{body}", encoding="utf-8")

    # Change status to approved (frontmatter-only edit)
    fm["status"] = "approved"
    fm_str_new = yaml.dump(fm, default_flow_style=False)
    vault_file.write_text(f"---\n{fm_str_new}---\n{body}", encoding="utf-8")

    result = detect_divergence(str(vault_file))
    assert result.diverged is False


# ---------- get_next_version ----------


def test_get_next_version_empty_folder(tmp_path):
    cfg = VaultConfig(vault_path=str(tmp_path), folder_prefix="PM Agent")
    assert get_next_version("prfaq", "test-product", cfg) == "1.0"


def test_get_next_version_with_existing(tmp_path):
    folder = tmp_path / "PM Agent" / "test-product"
    folder.mkdir(parents=True)
    (folder / "prfaq_v1.0.md").write_text("content", encoding="utf-8")
    cfg = VaultConfig(vault_path=str(tmp_path), folder_prefix="PM Agent")
    assert get_next_version("prfaq", "test-product", cfg) == "1.1"


def test_get_next_version_multiple_existing(tmp_path):
    folder = tmp_path / "PM Agent" / "test-product"
    folder.mkdir(parents=True)
    (folder / "prfaq_v1.0.md").write_text("content", encoding="utf-8")
    (folder / "prfaq_v1.1.md").write_text("content", encoding="utf-8")
    cfg = VaultConfig(vault_path=str(tmp_path), folder_prefix="PM Agent")
    assert get_next_version("prfaq", "test-product", cfg) == "1.2"


# ---------- mark_superseded ----------


def test_mark_superseded(tmp_path):
    fm = {"title": "Test", "version": "1.0", "status": "draft"}
    fm_str = yaml.dump(fm, default_flow_style=False)
    vault_file = tmp_path / "prfaq_v1.0.md"
    vault_file.write_text(f"---\n{fm_str}---\n# Body", encoding="utf-8")

    mark_superseded(str(vault_file), "prfaq_v1.1")

    content = vault_file.read_text(encoding="utf-8")
    assert "superseded_by" in content
    assert "[[prfaq_v1.1]]" in content
    assert "superseded" in content  # status changed


# ---------- get_product_slug ----------


def test_get_product_slug_from_feature_summary():
    slug = get_product_slug({"feature_summary": "Analytics Dashboard for E-Commerce"})
    assert slug == "analytics-dashboard-for-e-commerce"


def test_get_product_slug_prefers_product_name():
    slug = get_product_slug({
        "feature_summary": "A very long feature summary that would make a bad folder name",
        "product_name": "Analytics Dashboard",
    })
    assert slug == "analytics-dashboard"


def test_get_product_slug_special_chars():
    slug = get_product_slug({"feature_summary": "Foo! Bar? (Baz) #123"})
    assert slug == "foo-bar-baz-123"


# ---------- get_vault_config ----------


def test_vault_disabled_when_no_env_var(monkeypatch):
    monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)
    assert get_vault_config() is None


def test_vault_disabled_when_path_doesnt_exist(monkeypatch, tmp_path):
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path / "nonexistent"))
    assert get_vault_config() is None


def test_vault_enabled_when_path_exists(monkeypatch, tmp_path):
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    cfg = get_vault_config()
    assert cfg is not None
    assert cfg.vault_path == str(tmp_path)
    assert cfg.folder_prefix == "PM Agent"


# ---------- Integration: write_to_vault + generate_index_note ----------


def test_write_to_vault_creates_file(tmp_path):
    cfg = VaultConfig(vault_path=str(tmp_path), folder_prefix="PM Agent")
    markdown = "# Test PRFAQ\n\nContent here."
    path = write_to_vault(markdown, "prfaq", "test-product", "1.0", cfg,
                          upstream="research_brief", downstream="brd")
    assert path
    assert Path(path).exists()
    content = Path(path).read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert "artifact_type: prfaq" in content
    assert "original_hash:" in content
    assert "**Artifact chain:**" in content


def test_generate_index_note(tmp_path):
    cfg = VaultConfig(vault_path=str(tmp_path), folder_prefix="PM Agent")

    # Write a PRFAQ so the index has something to list
    write_to_vault("# PRFAQ\n\nContent.", "prfaq", "test-product", "1.0", cfg)

    path = generate_index_note("test-product", cfg, input_path="examples/input.yaml")
    assert path
    content = Path(path).read_text(encoding="utf-8")
    assert "PRFAQ" in content
    assert "[[prfaq_v1.0]]" in content
    assert "not yet generated" in content  # other artifacts missing


def test_full_pipeline_writes_to_vault(tmp_path):
    """Set vault to a temp dir, write all four artifacts, verify structure."""
    cfg = VaultConfig(vault_path=str(tmp_path), folder_prefix="PM Agent")
    slug = "test-product"

    write_to_vault("# Research\n\nBrief.", "research_brief", slug, "1.0", cfg,
                   downstream="prfaq")
    write_to_vault("# PRFAQ\n\nContent.", "prfaq", slug, "1.0", cfg,
                   upstream="research_brief", downstream="brd")
    write_to_vault("# BRD\n\nRequirements.", "brd", slug, "1.0", cfg,
                   upstream="prfaq", downstream="build_spec")
    write_to_vault("# Build Spec\n\nSpec.", "build_spec", slug, "1.0", cfg,
                   upstream="brd")

    generate_index_note(slug, cfg, input_path="examples/input.yaml")

    folder = tmp_path / "PM Agent" / slug
    assert (folder / "research_brief_v1.0.md").exists()
    assert (folder / "prfaq_v1.0.md").exists()
    assert (folder / "brd_v1.0.md").exists()
    assert (folder / "build_spec_v1.0.md").exists()
    assert (folder / "_index.md").exists()

    # Verify _index.md lists all four artifacts
    index_content = (folder / "_index.md").read_text(encoding="utf-8")
    assert "[[research_brief_v1.0]]" in index_content
    assert "[[prfaq_v1.0]]" in index_content
    assert "[[brd_v1.0]]" in index_content
    assert "[[build_spec_v1.0]]" in index_content
    assert "not yet generated" not in index_content

    # Verify frontmatter on one artifact
    prfaq_content = (folder / "prfaq_v1.0.md").read_text(encoding="utf-8")
    assert "artifact_type: prfaq" in prfaq_content
    assert "product_slug: test-product" in prfaq_content
    assert "upstream:" in prfaq_content
    assert "downstream:" in prfaq_content

    # Verify global MOC was generated
    moc = tmp_path / "PM Agent" / "_all_products.md"
    assert moc.exists()
    moc_content = moc.read_text(encoding="utf-8")
    assert "test-product" in moc_content.lower() or "Test Product" in moc_content


def test_initiative_nesting(tmp_path):
    """Products with initiative create a nested folder structure."""
    cfg = VaultConfig(vault_path=str(tmp_path), folder_prefix="PM Agent",
                      initiative="commerce-platform")

    write_to_vault("# PRFAQ\n\nContent.", "prfaq", "checkout", "1.0", cfg)

    nested = tmp_path / "PM Agent" / "commerce-platform" / "checkout" / "prfaq_v1.0.md"
    assert nested.exists()


# ---------- strip_frontmatter ----------


def test_strip_frontmatter_with_frontmatter():
    content = "---\ntitle: Test\nstatus: draft\n---\n# Hello\n\nBody text."
    result = strip_frontmatter(content)
    assert result == "# Hello\n\nBody text."
    assert "---" not in result
    assert "title:" not in result


def test_strip_frontmatter_without_frontmatter():
    content = "# Hello\n\nBody text."
    result = strip_frontmatter(content)
    assert result == content


def test_strip_frontmatter_removes_traceability():
    content = (
        "---\ntitle: Test\n---\n"
        "> **Artifact chain:** Research → **PRFAQ** → BRD\n\n"
        "# Hello\n\nBody."
    )
    result = strip_frontmatter(content)
    assert "Artifact chain" not in result
    assert "# Hello\n\nBody." in result


# ---------- resolve_artifact_path ----------


def test_resolve_artifact_path_vault_unmodified(tmp_path):
    """Vault copy exists, not diverged → returns vault path silently."""
    cfg = VaultConfig(vault_path=str(tmp_path), folder_prefix="PM Agent")
    write_to_vault("# PRFAQ\n\nContent.", "prfaq", "test", "1.0", cfg)

    output_file = tmp_path / "output" / "prfaq.md"
    output_file.parent.mkdir(parents=True)
    output_file.write_text("# PRFAQ\n\nOld content.", encoding="utf-8")

    result = resolve_artifact_path("prfaq", "test", cfg, str(output_file))
    # Should return the vault path (not the output path)
    assert "PM Agent" in result
    assert result.endswith("prfaq_v1.0.md")


def test_resolve_artifact_path_vault_diverged_accept(tmp_path):
    """Vault copy exists, diverged, user says 'y' → returns vault path."""
    cfg = VaultConfig(vault_path=str(tmp_path), folder_prefix="PM Agent")
    vault_path = write_to_vault("# PRFAQ\n\nContent.", "prfaq", "test", "1.0", cfg)

    # Modify the vault copy body to trigger divergence
    vp = Path(vault_path)
    content = vp.read_text(encoding="utf-8")
    vp.write_text(content.replace("Content.", "Edited by PM."), encoding="utf-8")

    output_file = tmp_path / "output" / "prfaq.md"
    output_file.parent.mkdir(parents=True)
    output_file.write_text("# PRFAQ\n\nContent.", encoding="utf-8")

    with patch("builtins.input", return_value="y"):
        result = resolve_artifact_path("prfaq", "test", cfg, str(output_file))
    assert result == vault_path


def test_resolve_artifact_path_vault_diverged_reject(tmp_path):
    """Vault copy exists, diverged, user says 'n' → returns output path."""
    cfg = VaultConfig(vault_path=str(tmp_path), folder_prefix="PM Agent")
    vault_path = write_to_vault("# PRFAQ\n\nContent.", "prfaq", "test", "1.0", cfg)

    # Modify the vault copy body
    vp = Path(vault_path)
    content = vp.read_text(encoding="utf-8")
    vp.write_text(content.replace("Content.", "Edited by PM."), encoding="utf-8")

    output_file = tmp_path / "output" / "prfaq.md"
    output_file.parent.mkdir(parents=True)
    output_file.write_text("# PRFAQ\n\nContent.", encoding="utf-8")

    with patch("builtins.input", return_value="n"):
        result = resolve_artifact_path("prfaq", "test", cfg, str(output_file))
    assert result == str(output_file)


def test_resolve_artifact_path_no_vault(tmp_path):
    """Vault not configured → returns output path."""
    output_file = tmp_path / "prfaq.md"
    output_file.write_text("# PRFAQ", encoding="utf-8")

    result = resolve_artifact_path("prfaq", "test", None, str(output_file))
    assert result == str(output_file)


def test_resolve_artifact_path_vault_missing_file(tmp_path):
    """Vault configured but file not in vault → returns output path."""
    cfg = VaultConfig(vault_path=str(tmp_path), folder_prefix="PM Agent")

    output_file = tmp_path / "prfaq.md"
    output_file.write_text("# PRFAQ", encoding="utf-8")

    result = resolve_artifact_path("prfaq", "test", cfg, str(output_file))
    assert result == str(output_file)
