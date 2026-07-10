"""Encoding-tolerant text file reads for PM-authored input files."""

from __future__ import annotations

from pathlib import Path


def read_text_lenient(path: str | Path) -> str:
    """Read a text file, tolerating the encodings Windows PM tools emit.

    Tries UTF-8 (BOM-aware) first, then cp1252 (Word/Outlook smart quotes,
    em dashes), then UTF-8 with replacement so a stray byte never crashes a
    run. Order matters: every valid UTF-8 file decodes on the first attempt,
    so the cp1252 fallback only fires on genuinely legacy bytes and can never
    corrupt UTF-8 content. utf-8-sig also strips a Windows Notepad UTF-8 BOM
    that would otherwise leak a leading U+FEFF into the first heading.
    """
    data = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")
