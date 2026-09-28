"""Small dependency-free JSON-RPC 2.0 helpers used by the demo servers."""

from __future__ import annotations

import json
import sys
from typing import Any, Callable


def response(request_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is None:
        message["result"] = result
    else:
        message["error"] = error
    return message


def serve(name: str, version: str, tools: list[dict[str, Any]], handlers: dict[str, Callable[[dict[str, Any]], Any]]) -> None:
    """Serve newline-delimited JSON-RPC over stdio."""
    for line in sys.stdin:
        if not line.strip():
            continue
        request = json.loads(line)
        method = request.get("method")
        request_id = request.get("id")
        if method == "initialize":
            result = {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": name, "version": version},
            }
            print(json.dumps(response(request_id, result), ensure_ascii=False), flush=True)
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            print(json.dumps(response(request_id, {"tools": tools}), ensure_ascii=False), flush=True)
        elif method == "tools/call":
            params = request.get("params", {})
            tool_name = params.get("name")
            try:
                if tool_name not in handlers:
                    raise ValueError(f"unknown tool: {tool_name}")
                result = handlers[tool_name](params.get("arguments", {}))
                print(json.dumps(response(request_id, result), ensure_ascii=False), flush=True)
            except Exception as exc:
                print(json.dumps(response(request_id, error={"code": -32000, "message": str(exc)}), ensure_ascii=False), flush=True)
        else:
            print(json.dumps(response(request_id, error={"code": -32601, "message": f"method not found: {method}"}), ensure_ascii=False), flush=True)
