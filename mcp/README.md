# MCP Set E - MCP package-registry task

## Run

From the repository root:

```powershell
python -m mcp.capture_demo
python -m mcp.agent mcp/config_server1.json
python -m mcp.agent mcp/config_server1_plus_2.json
```

The capture script calls `tools/list` from both configurations and calls the discovered `lookup_package_version` tool through the second server. It writes the required artifacts beside this README.

## What to show

1. Open `agent_diff.txt`: it must say `(zero changed lines)`.
2. Open `config.diff`: the only functional change is the second MCP server entry.
3. Open `tool_counts.md`: it shows `2 before -> 4 after` and names every tool from live `tools/list` responses.
4. Open `wire.json`: explain `jsonrpc`, `id`, `method`, `params`, `result`, and `error` for each exchange.
5. Run the discovered package lookup and point to `lookup_package_version` in the trace.
6. Open `error_before_after.md`: explain why a useful error lets the host model recover instead of guessing.
7. Open `risk_note.md`: read the five supply-chain lines exactly.

## Demo explanation

The host is the application containing the model. The client is the MCP transport connection. The servers expose tools and return data; they do not call the model. Adding server two is therefore a configuration change, and discovery supplies the new tool list at runtime.
