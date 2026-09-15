from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from week7.benchmark import run_benchmark
from week7.inputs import DocumentationCorpus, load_scenarios
from week7.limits import CircuitBreaker, CircuitBreakerTriggered
from week7.schemas import BenchmarkLimits, SchemaError
from week7.tools import ToolRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_ROOT = PROJECT_ROOT / "input_files 1" / "input_files"


class Week7Tests(unittest.TestCase):
    def test_loads_ten_mixed_migration_scenarios(self) -> None:
        scenarios = load_scenarios(INPUT_ROOT, scenario_count=10)
        self.assertEqual(len(scenarios), 10)
        self.assertEqual(sum(item.dependency_class != "fixed_documentation_path" for item in scenarios), 3)
        self.assertTrue(all(scenario.source_files for scenario in scenarios))

    def test_tool_registry_has_required_third_tool(self) -> None:
        scenarios = load_scenarios(INPUT_ROOT, scenario_count=3)
        corpus = DocumentationCorpus.from_directory(INPUT_ROOT / "developer_documentations")
        registry = ToolRegistry(corpus, scenarios)
        self.assertEqual(list(registry.definitions), ["search_documentation", "inspect_source", "check_deprecation"])
        result = registry.execute(
            "check_deprecation",
            {
                "api_version": "2025-06-01",
                "endpoint": "POST /repos/{owner}/{repo}/issues",
                "parameter": "assignee",
            },
        )
        self.assertTrue(result["deprecated"])
        self.assertEqual(result["replacement"], "assignees")
        with self.assertRaises(SchemaError):
            registry.execute(
                "check_deprecation",
                {
                    "api_version": "v9",
                    "endpoint": "POST /user/repos",
                    "parameter": "private",
                },
            )

    def test_unknown_tool_arguments_are_rejected(self) -> None:
        scenarios = load_scenarios(INPUT_ROOT, scenario_count=1)
        corpus = DocumentationCorpus.from_directory(INPUT_ROOT / "developer_documentations")
        registry = ToolRegistry(corpus, scenarios)
        with self.assertRaises(SchemaError):
            registry.execute("search_documentation", {"query": "x", "unexpected": True})

    def test_cost_and_iteration_breakers_abort(self) -> None:
        breaker = CircuitBreaker(BenchmarkLimits(max_iterations=1))
        breaker.start()
        breaker.begin_iteration()
        with self.assertRaises(CircuitBreakerTriggered):
            breaker.begin_iteration()

    def test_benchmark_writes_submission_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temporary:
            report = run_benchmark(INPUT_ROOT, Path(temporary), scenario_count=2)
            self.assertEqual(report["metadata"]["tool_count"], 3)
            self.assertEqual(report["metadata"]["tool_names"][-1], "check_deprecation")
            self.assertIn("react_agent", report["architectures"])
            self.assertIn("deterministic_workflow", report["architectures"])
            self.assertTrue((Path(temporary) / "benchmark_results.json").exists())
            self.assertTrue((Path(temporary) / "architecture_verdict.md").exists())
            self.assertTrue((Path(temporary) / "race.csv").exists())
            self.assertTrue((Path(temporary) / "budget_termination.log").exists())
            self.assertTrue(report["budget_termination"]["clean_termination"])
            self.assertEqual(report["architectures"]["react_agent"]["metrics"]["successful_cases"], 2)
            json.loads((Path(temporary) / "benchmark_results.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()