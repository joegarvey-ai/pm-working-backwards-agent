import os
from typing import Type

import httpx
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


DOVETAIL_MCP_BASE = "https://dovetail.com/api/mcp"


class DovetailSearchInput(BaseModel):
    """Input schema for DovetailSearchTool."""

    query: str = Field(
        ...,
        description="Keyword or theme to search across the Dovetail workspace.",
    )
    action: str = Field(
        default="search",
        description=(
            "Action to perform: 'search' to search across workspace data, "
            "'highlights' to retrieve customer quotes and highlights, "
            "'insights' to list published insights for a project."
        ),
    )
    project_id: str = Field(
        default="",
        description="Optional Dovetail project ID to scope results to a specific project.",
    )


class DovetailSearchTool(BaseTool):
    name: str = "dovetail_research"
    description: str = (
        "Search the Dovetail UX research repository for customer interview "
        "transcripts, usability findings, published insights, and customer "
        "quotes. Supports searching by keyword/theme, retrieving highlights, "
        "and listing published insights."
    )
    args_schema: Type[BaseModel] = DovetailSearchInput

    def _get_headers(self) -> dict:
        token = os.getenv("DOVETAIL_API_TOKEN")
        if not token:
            raise ValueError("DOVETAIL_API_TOKEN not set in environment variables.")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _run(self, query: str, action: str = "search", project_id: str = "") -> str:
        try:
            headers = self._get_headers()
        except ValueError as e:
            return str(e)

        try:
            if action == "search":
                return self._search_workspace(query, headers, project_id)
            elif action == "highlights":
                return self._get_highlights(query, headers, project_id)
            elif action == "insights":
                return self._get_insights(query, headers, project_id)
            else:
                return f"Unknown action '{action}'. Use 'search', 'highlights', or 'insights'."
        except httpx.HTTPStatusError as e:
            return f"Dovetail API error (HTTP {e.response.status_code}): {e.response.text}"
        except Exception as e:
            return f"Error connecting to Dovetail: {e}"

    def _search_workspace(self, query: str, headers: dict, project_id: str) -> str:
        """Search across workspace data by keyword/theme."""
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search",
                "arguments": {"query": query},
            },
            "id": 1,
        }
        if project_id:
            payload["params"]["arguments"]["project_id"] = project_id

        response = httpx.post(DOVETAIL_MCP_BASE, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        result = data.get("result", {})
        content = result.get("content", [])
        if not content:
            return f"No Dovetail results found for query: {query}"

        formatted = []
        for item in content:
            text = item.get("text", "")
            if text:
                formatted.append(text)

        return "\n\n---\n\n".join(formatted) if formatted else f"No content returned for query: {query}"

    def _get_highlights(self, query: str, headers: dict, project_id: str) -> str:
        """Retrieve customer quotes and highlights."""
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "get_highlights",
                "arguments": {"query": query},
            },
            "id": 2,
        }
        if project_id:
            payload["params"]["arguments"]["project_id"] = project_id

        response = httpx.post(DOVETAIL_MCP_BASE, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        result = data.get("result", {})
        content = result.get("content", [])
        if not content:
            return f"No highlights found for query: {query}"

        formatted = []
        for item in content:
            text = item.get("text", "")
            if text:
                formatted.append(f"> {text}")

        return "\n\n".join(formatted) if formatted else f"No highlight content returned for query: {query}"

    def _get_insights(self, query: str, headers: dict, project_id: str) -> str:
        """List published insights for a project."""
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "get_insights",
                "arguments": {"query": query},
            },
            "id": 3,
        }
        if project_id:
            payload["params"]["arguments"]["project_id"] = project_id

        response = httpx.post(DOVETAIL_MCP_BASE, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        result = data.get("result", {})
        content = result.get("content", [])
        if not content:
            return f"No published insights found for query: {query}"

        formatted = []
        for item in content:
            text = item.get("text", "")
            if text:
                formatted.append(text)

        return "\n\n---\n\n".join(formatted) if formatted else f"No insight content returned for query: {query}"
