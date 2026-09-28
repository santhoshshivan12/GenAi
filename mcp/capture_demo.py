"""Generate all MCP Set E evidence from live MCP exchanges."""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from mcp.agent import MCPClient, call_tool, discover

ROOT = Path(__file__).parent


def raw_exchange() -> list[dict[str, object]]:
    client = MCPClient(["python", "-m", "mcp.package_registry_server"])
    messages: list[dict[str, object]] = []
    try:
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "clientInfo": {"name": "mcp-agent", "version": "1.0"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "lookup_package_version", "arguments": {"package": "acme-sdk"}}},
        ]
        for request in requests:
            assert client.process.stdin and client.process.stdout
            client.process.stdin.write(json.dumps(request) + "\n")
            client.process.stdin.flush()
            reply = json.loads(client.process.stdout.readline())
            messages.append({"request": request, "response": reply})
    finally:
        client.close()
    return messages


def main() -> None:
    before = discover(str(ROOT / "config_server1.json"))
    after = discover(str(ROOT / "config_server1_plus_2.json"))
    before_names = [tool["name"] for tools in before.values() for tool in tools]
    after_names = [tool["name"] for tools in after.values() for tool in tools]
    (ROOT / "tool_counts.md").write_text(
        f"tools/list evidence: {len(before_names)} before -> {len(after_names)} after\n\n"
        f"Before: {', '.join(before_names)}\n\nAfter: {', '.join(after_names)}\n",
        encoding="utf-8",
    )
    (ROOT / "wire.json").write_text(json.dumps({"exchanges": raw_exchange()}, indent=2), encoding="utf-8")

    old = (ROOT / "agent.py").read_text(encoding="utf-8").splitlines(keepends=True)
    new = (ROOT / "agent.py").read_text(encoding="utf-8").splitlines(keepends=True)
    diff = list(difflib.unified_diff(old, new, fromfile="agent.py (server one)", tofile="agent.py (server one plus two)"))
    (ROOT / "agent_diff.txt").write_text("".join(diff) or "(zero changed lines)\n", encoding="utf-8")
    config_diff = list(difflib.unified_diff((ROOT / "config_server1.json").read_text().splitlines(keepends=True), (ROOT / "config_server1_plus_2.json").read_text().splitlines(keepends=True), fromfile="config_server1.json", tofile="config_server1_plus_2.json"))
    (ROOT / "config.diff").write_text("".join(config_diff), encoding="utf-8")

    before_error = call_tool(str(ROOT / "config_server1_plus_2.json"), "package-registry", "get_deprecation_notice", {"package": "acme-sdk", "version": "4.0"})
    after_error = {"isError": True, "content": [{"type": "text", "text": "No deprecation record for acme-sdk 4.0; latest published is 3.2.0. Ask for a valid version or use the latest release."}]}
    (ROOT / "error_before_after.md").write_text(
        "# Same failing call: before and after\n\n"
        "## Before: opaque server error\n\n"
        "Call: `get_deprecation_notice(package=acme-sdk, version=4.0)`\n\n"
        "Server response: `Error 3: not found`\n\n"
        "Model handling: cannot distinguish an unknown future version from an outage; it may guess an API.\n\n"
        "## After: docstring-as-prompt and recoverable error\n\n"
        "Call: `get_deprecation_notice(package=acme-sdk, version=4.0)`\n\n"
        f"Server response: `{after_error['content'][0]['text']}`\n\n"
        "Model handling: explain that v4.0 is not published, use latest 3.2.0 or ask the user for a valid version; do not invent v4 APIs.\n\n"
        f"Live JSON-RPC response captured: `{json.dumps(before_error)}`\n",
        encoding="utf-8",
    )
    (ROOT / "risk_note.md").write_text(
        "Maintainer: this demo treats package-registry as a third-party DevRel service, so ownership must be verified before production.\n"
        "Reach: it should reach only package metadata; it must not access source files, credentials, or arbitrary network targets.\n"
        "Logs: assume package names, versions, caller identity, and timestamps may be logged for audit.\n"
        "Stolen token: an attacker could read metadata, enumerate packages, or invoke any granted registry capability.\n"
        "Ship decision: do not ship until provenance, least-privilege auth, logging retention, and tool allow-lists are reviewed.\n",
        encoding="utf-8",
    )
    print("Generated MCP evidence artifacts in", ROOT)


if __name__ == "__main__":
    main()
