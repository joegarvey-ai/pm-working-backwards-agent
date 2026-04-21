"""Dovetail MCP research tool.

Talks to Dovetail's MCP JSON-RPC endpoint at DOVETAIL_MCP_BASE_URL.

Supported actions (the agent picks one per call):

  search          Free-text search. Returns titles, IDs, and project_ids.
                  Use this first to discover relevant projects.
  insights        List insight documents in a project (needs project_id).
  insight_content Get the full markdown body of one insight (needs insight_id).
  highlights      Get tagged customer quotes from a project (needs project_id).
  data_content    Get the full content of a data entry such as an interview
                  transcript or survey response (needs data_id).
  deep_search     Convenience combo: search -> list insights for each project
                  found -> fetch full content of each insight. Returns the
                  richest data in a single call but is slower.
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Type

import httpx
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


# Dedicated file logger for Dovetail tool invocations. Writes to
# output/dovetail_calls.log so we can verify whether the agent called
# this tool during a run, what it asked for, and what came back.
_CALL_LOG_PATH = Path(os.getenv("OUTPUT_DIR", "./output")) / "dovetail_calls.log"


def _log_call(event: str, details: dict) -> None:
    """Append one JSON line to the Dovetail call log. Never raises."""
    try:
        _CALL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            **details,
        }
        with _CALL_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        # Logging must never break the tool.
        pass


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
def _dovetail_post_with_retry(url, json_payload, headers, timeout):
    response = httpx.post(url, json=json_payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response


DOVETAIL_MCP_BASE = os.getenv("DOVETAIL_MCP_BASE_URL", "https://dovetail.com/api/mcp")


class DovetailSearchInput(BaseModel):
    """Input schema for DovetailSearchTool.

    NOTE: 'query' is required even though technically only search and
    deep_search use it. Making it required ensures the LLM always passes
    a value when Bedrock serializes the tool schema. For ID-based actions
    (insight_content, data_content, highlights) pass a short descriptive
    phrase as the query; it will be ignored by those actions but still
    satisfies the schema requirement.
    """

    query: str = Field(
        ...,
        description=(
            "Required free-text query describing what you are looking for. "
            "For action='search' or 'deep_search' this is the search term. "
            "For ID-based actions it is just a description of what you are "
            "fetching (the action will use the ID field, not the query)."
        ),
    )
    action: str = Field(
        default="deep_search",
        description=(
            "Action to perform. Options: "
            "'deep_search' (recommended first call) searches the workspace "
            "then auto-fetches full insight content for every project found. "
            "'search' returns titles and IDs only (fast, metadata). "
            "'insights' lists insight docs in a project (needs project_id). "
            "'insight_content' fetches full markdown of one insight (needs insight_id). "
            "'highlights' fetches tagged customer quotes (needs project_id). "
            "'data_content' fetches full content of a data entry (needs data_id)."
        ),
    )
    project_id: str = Field(
        default="",
        description="Dovetail project ID. Required for 'insights' and 'highlights'.",
    )
    insight_id: str = Field(
        default="",
        description="Dovetail insight ID. Required for 'insight_content'.",
    )
    data_id: str = Field(
        default="",
        description="Dovetail data entry ID. Required for 'data_content'.",
    )
    limit: int = Field(
        default=10,
        description="Max results per sub-request (1 to 100).",
    )


class DovetailSearchTool(BaseTool):
    name: str = "dovetail_research"
    description: str = (
        "Search the Dovetail UX research repository for customer interview "
        "transcripts, usability findings, published insights, and customer "
        "quotes. Start with action='deep_search' and a keyword query to "
        "get full insight content in one call. Use 'search' for a fast "
        "metadata-only lookup, then drill in with 'insight_content', "
        "'highlights', or 'data_content' using the IDs returned."
    )
    args_schema: Type[BaseModel] = DovetailSearchInput

    def _get_headers(self) -> dict:
        token = os.getenv("DOVETAIL_API_TOKEN")
        if not token:
            raise ValueError("DOVETAIL_API_TOKEN not set in environment variables.")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

    def _call_mcp(self, tool_name: str, arguments: dict) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
            "id": 1,
        }
        response = _dovetail_post_with_retry(
            DOVETAIL_MCP_BASE, payload, self._get_headers(), 30
        )
        return response.json()

    @staticmethod
    def _extract_text(data: dict) -> str:
        """Pull the text payload from a Dovetail MCP response."""
        content = data.get("result", {}).get("content", [])
        if not content:
            return ""
        parts = [item.get("text", "") for item in content if item.get("text")]
        return "\n\n---\n\n".join(parts)

    @staticmethod
    def _parse_json_text(raw: str) -> dict:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    def _deep_search(self, query: str, limit: int) -> str:
        """Search -> list insights per project -> fetch each insight's content."""
        # 1. Workspace search
        search_data = self._call_mcp(
            "search_workspace", {"query": query, "limit": limit}
        )
        search_text = self._extract_text(search_data)
        parsed = self._parse_json_text(search_text.split("---")[0].strip())
        notes = parsed.get("data", {}).get("notes", [])

        # Collect unique project IDs from search results
        project_ids = list(dict.fromkeys(
            n["project_id"] for n in notes if n.get("project_id")
        ))[:5]  # cap at 5 projects

        if not project_ids:
            return search_text or f"No Dovetail results for: {query}"

        sections = [f"## Dovetail Search Results for: {query}\n"]
        sections.append(f"Found {parsed.get('data', {}).get('total', 0)} items "
                        f"across {len(project_ids)} project(s).\n")

        # 2. For each project, list insights and fetch their content
        for pid in project_ids:
            project_title = next(
                (n.get("project_title", pid) for n in notes if n.get("project_id") == pid),
                pid,
            )
            sections.append(f"\n### Project: {project_title} (ID: {pid})\n")

            # List insights
            insights_data = self._call_mcp(
                "list_project_insights", {"project_id": pid, "limit": limit}
            )
            insights_text = self._extract_text(insights_data)
            insights_parsed = self._parse_json_text(insights_text.split("---")[0].strip())
            insight_list = insights_parsed.get("data", [])

            if not insight_list:
                sections.append("No published insights in this project.\n")
                # Fall back to highlights
                hl_data = self._call_mcp(
                    "get_project_highlights", {"project_id": pid, "limit": limit}
                )
                hl_text = self._extract_text(hl_data)
                hl_parsed = self._parse_json_text(hl_text.split("---")[0].strip())
                hl_list = hl_parsed.get("data", [])
                if hl_list:
                    sections.append("#### Highlights (customer quotes):\n")
                    for hl in hl_list[:10]:
                        text = hl.get("text", "").strip()
                        if text and len(text) > 3:
                            sections.append(f'> "{text}"\n')
                continue

            # 3. Fetch full content of each insight
            for insight in insight_list[:5]:  # cap at 5 insights per project
                iid = insight.get("id", "")
                ititle = insight.get("title", "Untitled")
                sections.append(f"\n#### Insight: {ititle}\n")

                content_data = self._call_mcp(
                    "get_insight_content", {"insight_id": iid}
                )
                content_text = self._extract_text(content_data)
                content_parsed = self._parse_json_text(content_text.split("---")[0].strip())
                markdown = content_parsed.get("data", {}).get("content_markdown", "")

                if markdown.strip():
                    # Truncate long insights to keep context manageable
                    if len(markdown) > 6000:
                        markdown = markdown[:6000] + "\n\n[... truncated for length]"
                    sections.append(markdown + "\n")
                else:
                    sections.append("(No content body available for this insight.)\n")

            # Also grab highlights for this project
            hl_data = self._call_mcp(
                "get_project_highlights", {"project_id": pid, "limit": 10}
            )
            hl_text = self._extract_text(hl_data)
            hl_parsed = self._parse_json_text(hl_text.split("---")[0].strip())
            hl_list = hl_parsed.get("data", [])
            if hl_list:
                sections.append("\n#### Highlights (customer quotes):\n")
                for hl in hl_list[:10]:
                    text = hl.get("text", "").strip()
                    if text and len(text) > 3:
                        sections.append(f'> "{text}"\n')

        return "\n".join(sections)

    def _run(
        self,
        query: str = "",
        action: str = "deep_search",
        project_id: str = "",
        insight_id: str = "",
        data_id: str = "",
        limit: int = 10,
    ) -> str:
        _log_call("invocation", {
            "action": action,
            "query": query,
            "project_id": project_id,
            "insight_id": insight_id,
            "data_id": data_id,
            "limit": limit,
        })
        try:
            _ = self._get_headers()
        except ValueError as e:
            logger.warning("Dovetail auth error: %s", e)
            _log_call("auth_error", {"message": str(e)})
            return str(e)

        limit = max(1, min(int(limit or 10), 100))

        try:
            result = self._dispatch(query, action, project_id, insight_id, data_id, limit)
            _log_call("response", {
                "action": action,
                "response_chars": len(result),
                "response_preview": result[:300],
            })
            return result
        except httpx.HTTPStatusError as e:
            logger.warning("Dovetail API HTTP error (action=%s): %s", action, e)
            _log_call("http_error", {
                "action": action,
                "status": e.response.status_code,
                "body": e.response.text[:300],
            })
            return f"Dovetail API error (HTTP {e.response.status_code}): {e.response.text}"
        except Exception as e:
            logger.warning("Dovetail connection error (action=%s): %s", action, e)
            _log_call("exception", {
                "action": action,
                "type": type(e).__name__,
                "message": str(e),
            })
            return f"Error connecting to Dovetail: {e}"

    def _dispatch(
        self,
        query: str,
        action: str,
        project_id: str,
        insight_id: str,
        data_id: str,
        limit: int,
    ) -> str:
        if action == "deep_search":
            if not query.strip():
                return "Dovetail 'deep_search' requires a non-empty query."
            return self._deep_search(query, limit)

        if action == "search":
            if not query.strip():
                return "Dovetail 'search' requires a non-empty query."
            data = self._call_mcp(
                "search_workspace", {"query": query, "limit": limit}
            )
            text = self._extract_text(data)
            return text or f"No Dovetail results for: {query}"

        if action == "insights":
            if not project_id.strip():
                return (
                    "Dovetail 'insights' requires a project_id. "
                    "Run action='search' first to find one."
                )
            data = self._call_mcp(
                "list_project_insights",
                {"project_id": project_id, "limit": limit},
            )
            text = self._extract_text(data)
            return text or f"No insights for project: {project_id}"

        if action == "insight_content":
            if not insight_id.strip():
                return (
                    "Dovetail 'insight_content' requires an insight_id. "
                    "Run action='insights' with a project_id first."
                )
            data = self._call_mcp(
                "get_insight_content", {"insight_id": insight_id}
            )
            text = self._extract_text(data)
            parsed = self._parse_json_text(text)
            md = parsed.get("data", {}).get("content_markdown", "")
            return md if md.strip() else text or f"No content for insight: {insight_id}"

        if action == "highlights":
            if not project_id.strip():
                return (
                    "Dovetail 'highlights' requires a project_id. "
                    "Run action='search' first to find one."
                )
            data = self._call_mcp(
                "get_project_highlights",
                {"project_id": project_id, "limit": limit},
            )
            text = self._extract_text(data)
            return text or f"No highlights for project: {project_id}"

        if action == "data_content":
            if not data_id.strip():
                return "Dovetail 'data_content' requires a data_id."
            data = self._call_mcp(
                "get_data_content", {"data_id": data_id}
            )
            text = self._extract_text(data)
            parsed = self._parse_json_text(text)
            md = parsed.get("data", {}).get("content_markdown", "")
            return md if md.strip() else text or f"No content for data: {data_id}"

        return (
            f"Unknown action '{action}'. Use 'deep_search', 'search', "
            f"'insights', 'insight_content', 'highlights', or 'data_content'."
        )
