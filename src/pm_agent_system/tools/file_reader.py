import logging
import os
from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Filenames (case-insensitive) and substrings that name credential material.
# Refused even inside an allowed root, as defense in depth.
_SECRET_NAMES = {
    ".env",
    "credentials",
    "id_rsa",
    "id_ed25519",
    ".netrc",
    ".pgpass",
    ".htpasswd",
}
_SECRET_SUBSTRINGS = ("cookie", "secret", "_token", "id_rsa", "id_ed25519")


def _allowed_roots() -> list[Path]:
    """Directories FileReaderTool is permitted to read from.

    The agent picks the path to read, so reads are confined to roots that
    hold legitimate PM context: the working directory, the output
    directory, the input directory, the Obsidian vault (when configured),
    and any directories named in PM_AGENT_CONTEXT_DIRS (os.pathsep list).
    Everything else, including home-directory secret files, is refused.
    """
    roots: list[Path] = []

    def _add(p: str | None) -> None:
        if not p:
            return
        try:
            roots.append(Path(p).expanduser().resolve())
        except Exception:  # noqa: BLE001 — a bad path just does not widen the allowlist
            return

    _add(os.getcwd())
    _add(os.getenv("OUTPUT_DIR", "./output"))
    _add("./input")
    _add(os.getenv("OBSIDIAN_VAULT_PATH"))
    for extra in os.getenv("PM_AGENT_CONTEXT_DIRS", "").split(os.pathsep):
        _add(extra.strip())

    # De-duplicate while preserving order.
    seen: set[Path] = set()
    unique: list[Path] = []
    for r in roots:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return unique


def _is_within(target: Path, root: Path) -> bool:
    return target == root or root in target.parents


def _looks_like_secret(path: Path) -> bool:
    name = path.name.lower()
    if name in _SECRET_NAMES:
        return True
    return any(s in name for s in _SECRET_SUBSTRINGS)


class FileReaderInput(BaseModel):
    """Input schema for FileReaderTool."""

    file_path: str = Field(
        ..., description="Path to the file to read. Must sit under the project "
        "working directory, the output or input directory, the configured "
        "Obsidian vault, or a PM_AGENT_CONTEXT_DIRS entry."
    )


class FileReaderTool(BaseTool):
    name: str = "file_reader"
    description: str = (
        "Read local files provided by the PM as internal context. Supports "
        "markdown (.md), plain text (.txt), Word documents (.docx), and "
        "PDF files (.pdf). Returns the text content of the file. Reads are "
        "confined to the project working directory, the output and input "
        "directories, the configured Obsidian vault, and PM_AGENT_CONTEXT_DIRS."
    )
    args_schema: Type[BaseModel] = FileReaderInput

    def _run(self, file_path: str) -> str:
        try:
            path = Path(file_path).expanduser().resolve()
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not resolve path %r: %s", file_path, e)
            return f"Error: could not resolve path {file_path!r}."

        roots = _allowed_roots()
        if not any(_is_within(path, root) for root in roots):
            logger.warning("Refused read outside allowed roots: %s", path)
            return (
                f"Error: reading {path} is not permitted. FileReaderTool only "
                f"reads files under the project working directory, the output "
                f"or input directory, the Obsidian vault, or a directory listed "
                f"in PM_AGENT_CONTEXT_DIRS."
            )
        if _looks_like_secret(path):
            logger.warning("Refused read of credential-like file: %s", path)
            return f"Error: reading {path.name} is not permitted (looks like a credential file)."

        if not path.exists():
            logger.warning("File not found: %s", path)
            return f"Error: File not found at {path}"
        if not path.is_file():
            logger.warning("Not a file: %s", path)
            return f"Error: {path} is not a file."

        suffix = path.suffix.lower()

        try:
            if suffix in (".md", ".txt", ".yaml", ".yml", ".json"):
                return self._read_text(path)
            elif suffix == ".docx":
                return self._read_docx(path)
            elif suffix == ".pdf":
                return self._read_pdf(path)
            else:
                return self._read_text(path)
        except Exception as e:
            logger.warning("Error reading file %s: %s", path, e)
            return f"Error reading {path}: {e}"

    def _read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def _read_docx(self, path: Path) -> str:
        try:
            import docx
        except ImportError:
            return "Error: python-docx is not installed. Run: uv pip install python-docx"

        doc = docx.Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)

    def _read_pdf(self, path: Path) -> str:
        try:
            import pdfplumber
        except ImportError:
            return "Error: pdfplumber is not installed. Run: uv pip install pdfplumber"

        text_parts = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)

        return "\n\n".join(text_parts) if text_parts else "No extractable text found in PDF."
