import json
import logging
import shutil
import subprocess
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_MCP_SERVER = "awslabs.aws-documentation-mcp-server@latest"


def _uvx_available() -> bool:
    return shutil.which("uvx") is not None


def _call_mcp(tool_name: str, arguments: dict) -> str:
    """Send a single MCP tool call to the AWS docs server via uvx and return the text content.

    Performs the required MCP initialize handshake before the tool call.
    """
    init_msg = json.dumps({
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "pm-agent", "version": "1.0"},
        },
        "id": 0,
    })
    initialized_msg = json.dumps({
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    })
    tool_msg = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    })
    payload = init_msg + "\n" + initialized_msg + "\n" + tool_msg + "\n"

    try:
        result = subprocess.run(
            ["uvx", _MCP_SERVER],
            input=payload,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return "Error: AWS docs MCP server timed out."
    except FileNotFoundError:
        return "Error: uvx not found. Install uv to enable AWS docs lookup."

    if result.returncode != 0:
        logger.warning("AWS docs MCP stderr: %s", result.stderr)

    # Parse the tool call response (id=1) from the output
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            response = json.loads(line)
        except json.JSONDecodeError:
            continue
        if response.get("id") != 1:
            continue

        error = response.get("error")
        if error:
            return f"MCP error {error.get('code')}: {error.get('message')}"

        content_blocks = response.get("result", {}).get("content", [])
        texts = [block.get("text", "") for block in content_blocks if block.get("type") == "text"]
        return "\n\n".join(texts) if texts else "No content returned."

    return f"Error: no response received for tool call '{tool_name}'"


# ---------------------------------------------------------------------------
# Search tool
# ---------------------------------------------------------------------------


class AWSDocsSearchInput(BaseModel):
    query: str = Field(..., description="Search query for AWS documentation.")
    limit: int = Field(default=5, description="Maximum number of results to return (1-10).")


class AWSDocsSearchTool(BaseTool):
    name: str = "aws_docs_search"
    description: str = (
        "Search official AWS documentation for service details, API references, "
        "architecture guidance, and best practices. Use this when you need accurate "
        "AWS service information for architecture decisions, cost flags, or code samples."
    )
    args_schema: Type[BaseModel] = AWSDocsSearchInput

    def _run(self, query: str, limit: int = 5) -> str:
        if not _uvx_available():
            return "Error: uvx not found. Install uv to enable AWS docs lookup."
        return _call_mcp("search_documentation", {"search_phrase": query, "limit": limit})


# ---------------------------------------------------------------------------
# Read tool
# ---------------------------------------------------------------------------


class AWSDocsReadInput(BaseModel):
    url: str = Field(..., description="Full URL of the AWS documentation page to read.")


class AWSDocsReadTool(BaseTool):
    name: str = "aws_docs_read"
    description: str = (
        "Fetch and read the full content of a specific AWS documentation page by URL. "
        "Use after aws_docs_search to get complete details from a result URL."
    )
    args_schema: Type[BaseModel] = AWSDocsReadInput

    def _run(self, url: str) -> str:
        if not _uvx_available():
            return "Error: uvx not found. Install uv to enable AWS docs lookup."
        return _call_mcp("read_documentation", {"url": url})
