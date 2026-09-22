from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from week7.inputs import DocumentationCorpus, load_scenarios
from week7.tools import ToolRegistry
from week8.evaluation import run_trajectory_evaluation, semantic_arguments_valid
from week8.expected import ALTERNATE_PATH_CASES, EXPECTED_TRAJECTORIES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_ROOT = PROJECT_ROOT / "input_files 1" / "input_files"


class Week8TrajectoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenarios = load_scenarios(INPUT_ROOT, scenario_count=10)
        cls.corpus = DocumentationCorpus.from_directory(INPUT_ROOT / "developer_documentations")
        cls.registry = ToolRegistry(cls.corpus, cls.scenarios)

    def test_all_ten_cases_have_asserted_paths(self) -> None:
        self.assertEqual(set(EXPECTED_TRAJECTORIES), {item.scenario_id for item in self.scenarios})
        self.assertEqual(ALTERNATE_PATH_CASES, {"hard-03", "hard-05", "hard-10"})
        self.assertTrue(all(EXPECTED_TRAJECTORIES.values()))

    def test_semantic_validation_rejects_fluent_fiction(self) -> None:
        valid, reason = semantic_arguments_valid(
            "check_deprecation",
            {
                "api_version": "2025-06-01",
                "endpoint": "POST /repos/{owner}/{repo}/teleport",
                "parameter": "quantum_mode",
            },
            self.registry,
        )
        self.assertFalse(valid)
        self.assertIn("not in the evaluated API", reason)

    def test_single_mitigation_closes_top_mode_and_writes_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temporary:
            report = run_trajectory_evaluation(INPUT_ROOT, Path(temporary))
            self.assertEqual(report["before"]["metrics"]["outcome_pass_rate_pct"], 100.0)
            self.assertEqual(report["before"]["metrics"]["trajectory_pass_rate_pct"], 70.0)
            self.assertEqual(
                report["before"]["metrics"]["outcome_vs_trajectory_gap_percentage_points"], 30.0
            )
            self.assertEqual(report["mitigation"]["name"], "re-planning")
            self.assertEqual(report["mitigation"]["before_count"], 3)
            self.assertEqual(report["mitigation"]["after_count"], 0)
            self.assertGreater(report["mitigation"]["price"]["p50_tokens"], 0)
            self.assertFalse(report["regression_summary"]["worsened_or_new"])
            self.assertTrue((Path(temporary) / "trajectory_results.json").exists())
            self.assertTrue((Path(temporary) / "trajectory_results.md").exists())


if __name__ == "__main__":
    unittest.main()
