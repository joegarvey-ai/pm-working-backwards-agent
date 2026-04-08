import os
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from tavily import TavilyClient


class TavilySearchInput(BaseModel):
    """Input schema for TavilySearchTool."""

    query: str = Field(
        ..., description="The search query to run against Tavily."
    )
    max_results: int = Field(
        default=5,
        description="Maximum number of results to return (1-10).",
    )
    search_depth: str = Field(
        default="advanced",
        description="Search depth: 'basic' for fast results, 'advanced' for comprehensive.",
    )


class TavilySearchTool(BaseTool):
    name: str = "tavily_search"
    description: str = (
        "Search the web for market data, competitor information, public customer "
        "feedback, industry benchmarks, and other external research. Returns "
        "titles, URLs, and content snippets for each result."
    )
    args_schema: Type[BaseModel] = TavilySearchInput

    def _run(self, query: str, max_results: int = 5, search_depth: str = "advanced") -> str:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return "Error: TAVILY_API_KEY not set in environment variables."

        try:
            client = TavilyClient(api_key=api_key)
            response = client.search(
                query=query,
                max_results=max_results,
                search_depth=search_depth,
            )
        except Exception as e:
            return f"Error performing Tavily search: {e}"

        results = response.get("results", [])
        if not results:
            return f"No results found for query: {query}"

        formatted = []
        for i, result in enumerate(results, 1):
            title = result.get("title", "No title")
            url = result.get("url", "No URL")
            content = result.get("content", "No content")
            formatted.append(f"### Result {i}\n**{title}**\n{url}\n\n{content}")

        return "\n\n---\n\n".join(formatted)
