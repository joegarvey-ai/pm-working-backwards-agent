"""Search prior pipeline outputs for reusable findings.

Scans the output/ directory (and optionally archive/) for research
briefs, PRFAQs, and BRDs that mention a keyword or topic. Useful
when the PM wants to know "what did we learn about X last time?"
"""

import logging
import os
from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

PREVIEW_CHARS = 300
MAX_RESULTS = 10


class PriorArtSearchInput(BaseModel):
    query: str = Field(..., description="Keyword or phrase to search for in prior outputs.")
    include_archive: bool = Field(
        default=False,
        description="Whether to also search the archive/ subdirectory.",
    )


class PriorArtSearchTool(BaseTool):
    name: str = "prior_art_search"
    description: str = (
        "Search prior pipeline outputs (research briefs, PRFAQs, BRDs, build specs) "
        "for mentions of a keyword or topic. Use this to find reusable findings, "
        "avoid re-researching topics, or reference prior decisions. Searches the "
        "output/ directory by default; set include_archive=True to also search "
        "archived outputs."
    )
    args_schema: Type[BaseModel] = PriorArtSearchInput

    def _run(self, query: str, include_archive: bool = False) -> str:
        output_dir = Path(os.getenv("OUTPUT_DIR", "./output"))
        if not output_dir.exists():
            return "No output directory found. Run the pipeline at least once first."

        search_dirs = [output_dir]
        if include_archive:
            archive = output_dir / "archive"
            if archive.exists():
                search_dirs.append(archive)

        q = query.lower()
        results: list[str] = []

        for search_dir in search_dirs:
            for path in sorted(search_dir.glob("*.md"), reverse=True):
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                lower = text.lower()
                idx = lower.find(q)
                if idx == -1:
                    continue

                start = max(0, idx - 60)
                preview = text[start : start + PREVIEW_CHARS].replace("\n", " ").strip()
                label = "archive" if "archive" in str(path) else "live"
                results.append(f"- [{label}] {path.name}\n  ...{preview}...")

                if len(results) >= MAX_RESULTS:
                    break

        if not results:
            return f"No prior outputs mention '{query}'."

        return f"Found {len(results)} prior outputs mentioning '{query}':\n\n" + "\n\n".join(results)
