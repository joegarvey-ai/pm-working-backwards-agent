import logging
import os
from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Default style guide path is resolved relative to the project root at
# runtime. Override by setting the STYLE_GUIDE_PATH environment variable.
DEFAULT_STYLE_GUIDE_PATH = "examples/templates/style-guide-sample.md"

FALLBACK_MESSAGE = (
    "No style guide configured. Using default writing rules from the agent "
    "backstory. Apply those rules strictly."
)


class StyleGuideLoaderInput(BaseModel):
    """No arguments. The loader resolves the path from STYLE_GUIDE_PATH or default."""


class StyleGuideLoaderTool(BaseTool):
    name: str = "style_guide_loader"
    description: str = (
        "Load the writing style guide from disk and return its full text. "
        "Reads from STYLE_GUIDE_PATH env var if set, otherwise falls back to "
        "examples/templates/style-guide-sample.md in the project root. Call this once "
        "before drafting any prose so the rules are in working memory. "
        "Takes no arguments."
    )
    args_schema: Type[BaseModel] = StyleGuideLoaderInput

    def _run(self) -> str:
        configured = os.getenv("STYLE_GUIDE_PATH", "").strip()
        path_str = configured or DEFAULT_STYLE_GUIDE_PATH
        path = Path(path_str).expanduser()

        # If the path is relative, resolve it against the current working dir
        # (typically the project root when running via the CLI entry point).
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()

        if not path.exists() or not path.is_file():
            logger.warning("Style guide not found at %s, using fallback", path)
            return FALLBACK_MESSAGE

        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Error loading style guide from %s: %s", path, e)
            return f"{FALLBACK_MESSAGE} (load error: {e})"
