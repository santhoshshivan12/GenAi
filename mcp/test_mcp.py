"""Automated acceptance tests for MCP Task Set E."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from mcp.agent import call_tool, discover


ROOT = Path(__file__).parent


class Week9MCPTests(unittest.TestCase):
    def test_server_one_discovers_two_tools(self) -> None:
        tools = discover(str(ROOT / "config_server1.json"))
        names = [tool["name"] for item in tools.values() for tool in item]
        self.assertEqual(names, ["search_docs", "inspect_doc"])

    def test_server_two_is_config_only_and_discovers_four_tools(self) -> None:
        tools = discover(str(ROOT / "config_server1_plus_2.json"))
        names = [tool["name"] for item in tools.values() for tool in item]
        self.assertEqual(names, ["search_docs", "inspect_doc", "lookup_package_version", "get_deprecation_notice"])

    def test_package_registry_lookup_is_called_through_mcp(self) -> None:
        response = call_tool(str(ROOT / "config_server1_plus_2.json"), "package-registry", "lookup_package_version", {"package": "acme-sdk"})
        text = response["result"]["content"][0]["text"]
        self.assertIn("3.2.0", text)
        self.assertIn("2026-01-15", text)

    def test_unknown_version_is_recoverable(self) -> None:
        response = call_tool(str(ROOT / "config_server1_plus_2.json"), "package-registry", "get_deprecation_notice", {"package": "acme-sdk", "version": "4.0"})
        result = response["result"]
        self.assertTrue(result["isError"])
        self.assertIn("latest published is 3.2.0", result["content"][0]["text"])

    def test_required_evidence_files_exist(self) -> None:
        required = ["agent_diff.txt", "config.diff", "wire.json", "tool_counts.md", "error_before_after.md", "risk_note.md"]
        for filename in required:
            self.assertTrue((ROOT / filename).exists(), filename)

        wire = json.loads((ROOT / "wire.json").read_text(encoding="utf-8"))
        self.assertEqual([item["request"]["method"] for item in wire["exchanges"]], ["initialize", "tools/list", "tools/call"])

        risk_lines = (ROOT / "risk_note.md").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(risk_lines), 5)


if __name__ == "__main__":
    unittest.main()
