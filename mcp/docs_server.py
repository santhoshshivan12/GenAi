"""Own MCP server: searchable developer documentation."""

from __future__ import annotations

import sys
from pathlib import Path

from mcp.mcp_protocol import serve


TOOLS = [
    {
        "name": "search_docs",
        "description": "Search the local developer documentation for a query.",
        "inputSchema": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}},
    },
    {
        "name": "inspect_doc",
        "description": "Read a named local documentation page.",
        "inputSchema": {"type": "object", "required": ["page"], "properties": {"page": {"type": "string"}}},
    },
]

DOCS = {
    "mcp": "MCP is a standard socket between a host, client, and server. The model runs in the host; the server exposes capabilities.",
    "migration": "For v3 migration, check the package registry version and deprecation notices before writing code.",
}


def search_docs(arguments: dict[str, str]) -> dict[str, object]:
    query = arguments.get("query", "").lower()
    hits = [{"page": key, "text": value} for key, value in DOCS.items() if any(word in value.lower() for word in query.split())]
    return {"content": [{"type": "text", "text": str({"hits": hits, "count": len(hits)})}]}


def inspect_doc(arguments: dict[str, str]) -> dict[str, object]:
    page = arguments.get("page", "")
    if page not in DOCS:
        return {"isError": True, "content": [{"type": "text", "text": f"No documentation page named {page}"}]}
    return {"content": [{"type": "text", "text": DOCS[page]}]}


if __name__ == "__main__":
    serve("docs-search", "1.0.0", TOOLS, {"search_docs": search_docs, "inspect_doc": inspect_doc})
