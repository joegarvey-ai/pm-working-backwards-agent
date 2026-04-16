"""Textual TUI viewer for pipeline output artifacts.

Run in terminal:  uv run pm_agent_system view [file.md]
Serve to browser:  uv run pm_agent_system view --serve [file.md]
"""

from __future__ import annotations

import os
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    DirectoryTree,
    Footer,
    Header,
    Markdown,
    Static,
)


class FilteredTree(DirectoryTree):
    """Directory tree that only shows markdown files."""

    def filter_paths(self, paths: list[Path]) -> list[Path]:
        return sorted(
            [
                p
                for p in paths
                if p.is_dir() or p.suffix == ".md"
            ],
            key=lambda p: (p.is_file(), p.name),
        )


class ArtifactViewer(App):
    """Browse and read pipeline output artifacts."""

    TITLE = "PM Working Backwards Agent"
    SUB_TITLE = "Artifact Viewer"

    CSS = """
    #sidebar {
        width: 35;
        dock: left;
        background: $surface;
        border-right: solid $primary;
    }
    #content {
        width: 1fr;
        padding: 1 2;
        overflow-y: auto;
    }
    #status-bar {
        height: 1;
        dock: bottom;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    FilteredTree {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("t", "toggle_sidebar", "Toggle sidebar"),
    ]

    def __init__(
        self,
        output_dir: str | Path | None = None,
        initial_file: str | Path | None = None,
    ) -> None:
        super().__init__()
        self._output_dir = Path(
            output_dir or os.getenv("OUTPUT_DIR", "./output")
        ).resolve()
        self._initial_file = Path(initial_file).resolve() if initial_file else None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="sidebar"):
                yield FilteredTree(str(self._output_dir))
            yield Markdown("# Welcome\n\nSelect a file from the sidebar to view it.", id="content")
        yield Static("Ready", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        if self._initial_file and self._initial_file.exists():
            self._load_file(self._initial_file)

    @on(DirectoryTree.FileSelected)
    def on_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        path = Path(event.path)
        if path.suffix == ".md":
            self._load_file(path)

    def _load_file(self, path: Path) -> None:
        try:
            content = path.read_text(encoding="utf-8")
            md = self.query_one("#content", Markdown)
            md.update(content)
            status = self.query_one("#status-bar", Static)
            status.update(f"Viewing: {path.name}")
        except Exception as exc:
            status = self.query_one("#status-bar", Static)
            status.update(f"Error: {exc}")

    def action_refresh(self) -> None:
        tree = self.query_one(FilteredTree)
        tree.reload()
        status = self.query_one("#status-bar", Static)
        status.update("Refreshed file list")

    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar")
        sidebar.display = not sidebar.display


def main() -> None:
    """CLI entry point for the viewer."""
    import sys

    initial_file = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None
    app = ArtifactViewer(initial_file=initial_file)
    app.run()


if __name__ == "__main__":
    main()
