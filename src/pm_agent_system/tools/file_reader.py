import os
from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class FileReaderInput(BaseModel):
    """Input schema for FileReaderTool."""

    file_path: str = Field(
        ..., description="Absolute or relative path to the file to read."
    )


class FileReaderTool(BaseTool):
    name: str = "file_reader"
    description: str = (
        "Read local files provided by the PM as internal context. Supports "
        "markdown (.md), plain text (.txt), Word documents (.docx), and "
        "PDF files (.pdf). Returns the text content of the file."
    )
    args_schema: Type[BaseModel] = FileReaderInput

    def _run(self, file_path: str) -> str:
        path = Path(file_path).expanduser().resolve()

        if not path.exists():
            return f"Error: File not found at {path}"
        if not path.is_file():
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
