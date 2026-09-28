# MCP MCP Task Set E - Complete Testing Documentation

This document explains exactly how to test and demonstrate the package-registry MCP task.

## 1. What must pass

The implementation is accepted when all six checks below pass:

1. The original agent module has zero changed lines.
2. The second MCP server is added through configuration only.
3. `tools/list` reports two tools before and four tools after.
4. A tool from the package-registry server is called successfully.
5. The unknown-version error is specific and recoverable.
6. The required evidence files are present and internally consistent.

## 2. Open PowerShell in the project root

```powershell
cd D:\Santhoshshivan\Python\PythonProject
```

If Python is not found, activate the project environment first:

```powershell
.\.venv\Scripts\Activate.ps1
```

No external package installation is required for this MCP implementation.

## 3. Basic syntax test

Compile every MCP Python file:

```powershell
python -m compileall -q mcp
```

Expected result: no error output.

## 4. Test server one discovery

Run:

```powershell
python -m mcp.agent mcp/config_server1.json
```

Expected result: one server named `docs-search` with these two tools:

```text
search_docs
inspect_doc
```

This is the baseline: `2 tools before`.

## 5. Test server one plus server two discovery

Run:

```powershell
python -m mcp.agent mcp/config_server1_plus_2.json
```

Expected result:

```text
docs-search:
  search_docs
  inspect_doc
package-registry:
  lookup_package_version
  get_deprecation_notice
```

This proves: `2 before -> 4 after`.

The important point is that `mcp/agent.py` was not edited to add these names. The names came from live `tools/list` responses.

## 6. Test the required package lookup

Run:

```powershell
python -c "from mcp.agent import call_tool; import json; print(json.dumps(call_tool('mcp/config_server1_plus_2.json','package-registry','lookup_package_version',{'package':'acme-sdk'}), indent=2))"
```

Expected result contains:

```text
lookup_package_version
acme-sdk
3.2.0
2026-01-15
```

This is the main proof that the second server was actually called.

## 7. Test the recoverable error

Run:

```powershell
python -c "from mcp.agent import call_tool; import json; print(json.dumps(call_tool('mcp/config_server1_plus_2.json','package-registry','get_deprecation_notice',{'package':'acme-sdk','version':'4.0'}), indent=2))"
```

Expected result contains:

```text
isError: true
No deprecation record for acme-sdk 4.0
latest published is 3.2.0
```

Explain that this is recoverable because the host model knows that v4.0 is not published and can use v3.2.0 or ask for a valid version. It does not mistake the condition for a registry outage or invent an API.

## 8. Run the automated acceptance tests

Run:

```powershell
python -m unittest mcp.test_mcp -v
```

Expected result:

```text
Ran 5 tests
OK
```

The tests verify discovery, the four-tool count, the live lookup, the recoverable error, the wire file, and the five-line risk note.

## 9. Inspect the submission evidence

Check the files:

```powershell
Get-ChildItem mcp\agent_diff.txt, mcp\config.diff, mcp\wire.json, mcp\tool_counts.md, mcp\error_before_after.md, mcp\risk_note.md
```

Review them in this order:

### `agent_diff.txt`

Must contain:

```text
(zero changed lines)
```

### `config.diff`

Must show the `package-registry` server being added to the configuration.

### `tool_counts.md`

Must show:

```text
2 before -> 4 after
```

### `wire.json`

Must show three exchanges in order:

```text
initialize -> tools/list -> tools/call
```

During the explanation, define these fields:

| Field | Explanation |
|---|---|
| `jsonrpc` | JSON-RPC protocol version. |
| `id` | Matches a response to its request. |
| `method` | Operation requested from the MCP server. |
| `params` | Arguments for the operation. |
| `result` | Successful response. |
| `error` | Failed response, if present. |
| `tools` | Tools discovered from the server. |
| `content` | Text or other content returned to the host. |

### `error_before_after.md`

Show the difference between:

```text
Error 3: not found
```

and the useful message containing the latest published version.

### `risk_note.md`

Confirm it has exactly five lines:

```powershell
(Get-Content mcp\risk_note.md).Count
```

Expected result: `5`.

## 10. Full mentor demo sequence

Use this sequence during the demo:

1. Open `config_server1.json` and explain that it contains only the docs-search server.
2. Run the baseline discovery command and show two tools.
3. Open `config_server1_plus_2.json` and point out only the new server entry.
4. Run the second discovery command and show four tools.
5. Run the package lookup command and point to `lookup_package_version` in the result.
6. Open `agent_diff.txt` and prove the agent has zero changed lines.
7. Open `wire.json` and explain initialize, tools/list, and tools/call.
8. Run the v4.0 failing call and explain the recoverable response.
9. Open `error_before_after.md` and compare the old and new model behavior.
10. Open `risk_note.md` and read the five supply-chain risk lines.
11. Run `python -m unittest mcp.test_mcp -v` and show `OK`.

## 11. Short explanation to memorize

“MCP is the connection standard between my host application and external tools. The host contains the model, the client manages the MCP connection, and the server exposes capabilities. I first discover two tools from my documentation server. Then I add the package-registry server only in configuration. Discovery now returns four tools, and the host successfully calls `lookup_package_version`. The agent code remains unchanged. The server does not call the model. Finally, the registry returns a recoverable message for an unknown version so the model does not guess.”

## 12. Troubleshooting

### `ModuleNotFoundError: No module named mcp`

Run commands from the repository root:

```powershell
cd D:\Santhoshshivan\Python\PythonProject
```

### A tool is missing

Check that the command uses `config_server1_plus_2.json`, not `config_server1.json`.

### The lookup does not show package metadata

Use the exact package name `acme-sdk`.

### The test count is different

Run the discovery commands again and ensure the server processes are not being replaced by another local MCP configuration.

### The demo window closes or hangs

Do not run the server module by itself. Run the agent commands, because the agent starts the server and sends JSON-RPC requests through stdin/stdout.
