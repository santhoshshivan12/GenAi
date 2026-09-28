"""Config-driven MCP host. This file is intentionally unchanged between demos."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


class MCPClient:
    def __init__(self, command: list[str]) -> None:
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.next_id = 1

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        if params is not None:
            request["params"] = params
        self.next_id += 1
        assert self.process.stdin and self.process.stdout
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())

    def close(self) -> None:
        self.process.terminate()


def discover(config_path: str) -> dict[str, list[dict[str, Any]]]:
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    discovered: dict[str, list[dict[str, Any]]] = {}
    for server in config["mcpServers"]:
        client = MCPClient(server["command"])
        try:
            client.request("initialize", {"clientInfo": {"name": "mcp-agent", "version": "1.0"}})
            result = client.request("tools/list")
            discovered[server["name"]] = result["result"]["tools"]
        finally:
            client.close()
    return discovered


def call_tool(config_path: str, server_name: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    server = next(item for item in config["mcpServers"] if item["name"] == server_name)
    client = MCPClient(server["command"])
    try:
        client.request("initialize", {"clientInfo": {"name": "mcp-agent", "version": "1.0"}})
        return client.request("tools/call", {"name": tool_name, "arguments": arguments})
    finally:
        client.close()


def model_call(tool_result: dict[str, Any]) -> str:
    """Host-side model boundary; the MCP server never calls an LLM."""
    return "The host model received the tool result and can explain the package metadata or recover from the error."


if __name__ == "__main__":
    config = sys.argv[1] if len(sys.argv) > 1 else "mcp/config_server1.json"
    print(json.dumps(discover(config), indent=2))
