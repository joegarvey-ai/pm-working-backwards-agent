"""Self-contained HTML export for pipeline artifacts.

Converts markdown to a standalone HTML document with inline CSS.
No CDN, no external stylesheets, no JavaScript. Works offline.
"""

from __future__ import annotations

from markdown_it import MarkdownIt

_md = MarkdownIt("commonmark").enable("table")

_CSS = """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    Helvetica, Neue, Arial, sans-serif;
  line-height: 1.6;
  color: #1a1a1a;
  background: #fff;
  padding: 2rem 1rem;
}
.container { max-width: 780px; margin: 0 auto; }
h1 { font-size: 1.8rem; margin: 1.5rem 0 0.75rem; border-bottom: 2px solid #e0e0e0; padding-bottom: 0.3rem; }
h2 { font-size: 1.4rem; margin: 1.3rem 0 0.6rem; border-bottom: 1px solid #eee; padding-bottom: 0.2rem; }
h3 { font-size: 1.15rem; margin: 1rem 0 0.5rem; }
h4 { font-size: 1rem; margin: 0.8rem 0 0.4rem; }
p { margin: 0.6rem 0; }
ul, ol { margin: 0.6rem 0 0.6rem 1.5rem; }
li { margin: 0.2rem 0; }
a { color: #0066cc; text-decoration: none; }
a:hover { text-decoration: underline; }
strong { font-weight: 600; }
em { font-style: italic; }
code {
  font-family: "SF Mono", Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 0.88em;
  background: #f4f4f4;
  padding: 0.15em 0.35em;
  border-radius: 3px;
}
pre {
  background: #f6f8fa;
  border: 1px solid #e1e4e8;
  border-radius: 6px;
  padding: 1rem;
  overflow-x: auto;
  margin: 0.8rem 0;
  line-height: 1.45;
}
pre code { background: none; padding: 0; font-size: 0.85em; }
table {
  border-collapse: collapse;
  width: 100%;
  margin: 0.8rem 0;
  font-size: 0.92em;
}
th, td {
  border: 1px solid #d0d7de;
  padding: 0.5rem 0.75rem;
  text-align: left;
}
th { background: #f6f8fa; font-weight: 600; }
tr:nth-child(even) { background: #fafbfc; }
blockquote {
  border-left: 4px solid #e8a838;
  background: #fff8e1;
  padding: 0.75rem 1rem;
  margin: 0.8rem 0;
  color: #5d4e37;
}
blockquote p { margin: 0.3rem 0; }
hr { border: none; border-top: 1px solid #e0e0e0; margin: 1.5rem 0; }
details { margin: 0.6rem 0; }
summary { cursor: pointer; font-weight: 600; }
@media (prefers-color-scheme: dark) {
  body { background: #0d1117; color: #c9d1d9; }
  h1, h2 { border-color: #30363d; }
  a { color: #58a6ff; }
  code { background: #161b22; }
  pre { background: #161b22; border-color: #30363d; }
  th { background: #161b22; }
  th, td { border-color: #30363d; }
  tr:nth-child(even) { background: #0d1117; }
  blockquote { background: #1c1a10; border-color: #d29922; color: #e3b341; }
}
"""


def markdown_to_html(markdown_text: str, title: str = "Artifact") -> str:
    """Convert a markdown string to a self-contained HTML document.

    The output is a complete HTML file with inline <style>, no external
    resources, and no JavaScript. Works offline in any browser.
    """
    # Strip YAML frontmatter before converting
    body = markdown_text
    if body.startswith("---"):
        end = body.find("\n---\n", 3)
        if end != -1:
            body = body[end + 5:]

    html_body = _md.render(body)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escape(title)}</title>
<style>
{_CSS}
</style>
</head>
<body>
<div class="container">
{html_body}
</div>
</body>
</html>
"""


def _escape(text: str) -> str:
    """Escape HTML special characters in a string."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
