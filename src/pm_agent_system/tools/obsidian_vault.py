import os
from pathlib import Path
from typing import Optional, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

# Default to "~/Obsidian" if OBSIDIAN_VAULT_PATH is not set. Set the env var
# to point at your own Obsidian vault, or leave it unset if you don't use
# Obsidian (the tools will simply return "vault not found").
DEFAULT_VAULT_PATH = "~/Obsidian"

PREVIEW_CHARS = 200
MAX_RESULTS = 25


def _vault_root() -> Path:
    return Path(os.getenv("OBSIDIAN_VAULT_PATH", DEFAULT_VAULT_PATH)).expanduser()


def _safe_resolve(rel: str) -> Optional[Path]:
    root = _vault_root().resolve()
    try:
        target = (root / rel).resolve()
    except Exception:
        return None
    if root not in target.parents and target != root:
        return None
    return target


class ObsidianSearchInput(BaseModel):
    query: str = Field(..., description="Keyword or phrase to search for in note contents.")
    folder: str = Field(
        "",
        description="Optional vault-relative folder to limit the search. Empty = whole vault.",
    )


class ObsidianSearchTool(BaseTool):
    name: str = "obsidian_search"
    description: str = (
        "Search the user's Obsidian vault for markdown notes containing a keyword or phrase. "
        "Optionally restrict to a vault-relative folder. Returns matching note paths with a "
        "short content preview. Use this to find prior notes, decisions, or research."
    )
    args_schema: Type[BaseModel] = ObsidianSearchInput

    def _run(self, query: str, folder: str = "") -> str:
        root = _vault_root()
        if not root.exists():
            return f"Obsidian vault not found at {root}"

        search_root = root
        if folder:
            resolved = _safe_resolve(folder)
            if resolved is None or not resolved.exists():
                return f"Folder '{folder}' not found in vault."
            search_root = resolved

        q = query.lower()
        results: list[str] = []
        for path in search_root.rglob("*.md"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            lower = text.lower()
            idx = lower.find(q)
            if idx == -1:
                continue
            start = max(0, idx - 40)
            preview = text[start : start + PREVIEW_CHARS].replace("\n", " ").strip()
            rel = path.relative_to(root)
            results.append(f"- {rel}\n  …{preview}…")
            if len(results) >= MAX_RESULTS:
                break

        if not results:
            return f"No notes found matching '{query}'" + (f" in {folder}" if folder else "")
        return f"Found {len(results)} matches for '{query}':\n\n" + "\n\n".join(results)


class ObsidianReadInput(BaseModel):
    path: str = Field(..., description="Vault-relative path to a markdown note (e.g. 'Folder/Note.md').")


class ObsidianReadTool(BaseTool):
    name: str = "obsidian_read"
    description: str = (
        "Read the full contents of a markdown note from the user's Obsidian vault by its "
        "vault-relative path. Use after obsidian_search to load a specific note."
    )
    args_schema: Type[BaseModel] = ObsidianReadInput

    def _run(self, path: str) -> str:
        target = _safe_resolve(path)
        if target is None:
            return f"Path '{path}' is outside the vault."
        if not target.exists() or not target.is_file():
            return f"Note '{path}' not found in vault."
        try:
            return target.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading '{path}': {e}"
