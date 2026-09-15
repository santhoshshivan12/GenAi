"""Runtime adapter for using the Week 7 runners from the chatbot UI."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from week7.architectures import DeterministicWorkflow, ReActAgent
from week7.benchmark import DEFAULT_INPUT_ROOT, DEFAULT_OUTPUT_DIR
from week7.inputs import DocumentationCorpus, load_scenarios
from week7.schemas import BenchmarkLimits
from week7.tools import ToolRegistry


class Week7ChatRuntime:
    def __init__(self) -> None:
        self.input_root = DEFAULT_INPUT_ROOT
        self.output_dir = DEFAULT_OUTPUT_DIR
        self.scenarios = load_scenarios(self.input_root, scenario_count=10)
        self.scenario_map = {scenario.scenario_id: scenario for scenario in self.scenarios}
        self.corpus = DocumentationCorpus.from_directory(self.input_root / "developer_documentations")
        self.registry = ToolRegistry(self.corpus, self.scenarios)
        self.limits = BenchmarkLimits()
        self.log_path = self.output_dir / "ui_runs.jsonl"
        self._log_lock = threading.Lock()

    def scenario_options(self) -> list[dict[str, Any]]:
        return [
            {
                "scenario_id": scenario.scenario_id,
                "level": scenario.level,
                "question": scenario.question,
                "dependency_class": scenario.dependency_class,
                "dependency_reason": scenario.dependency_reason,
                "source_files": scenario.source_files,
                "page_numbers": scenario.page_numbers,
            }
            for scenario in self.scenarios
        ]

    def run(self, scenario_id: str, architecture: str) -> dict[str, Any]:
        if scenario_id not in self.scenario_map:
            raise ValueError(f"Unknown Week 7 scenario: {scenario_id}")
        if architecture not in {"react_agent", "deterministic_workflow"}:
            raise ValueError("architecture must be react_agent or deterministic_workflow")

        scenario = self.scenario_map[scenario_id]
        runner = (
            ReActAgent(self.registry, self.limits)
            if architecture == "react_agent"
            else DeterministicWorkflow(self.registry, self.limits)
        )
        result = runner.run(scenario)
        payload = result.to_dict()
        payload.update(
            {
                "question": scenario.question,
                "level": scenario.level,
                "dependency_class": scenario.dependency_class,
                "dependency_reason": scenario.dependency_reason,
                "source_files": scenario.source_files,
                "page_numbers": scenario.page_numbers,
                "limits": self.limits.to_dict(),
                "budget_status": "aborted" if result.aborted else "within limits",
            }
        )
        self._append_log(payload)
        return payload

    def _append_log(self, payload: dict[str, Any]) -> None:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            with self._log_lock, self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except OSError:
            # UI execution should still return the result if a local log file
            # cannot be written in a restricted deployment environment.
            pass


_runtime: Week7ChatRuntime | None = None
_runtime_lock = threading.Lock()


def get_week7_runtime() -> Week7ChatRuntime:
    global _runtime
    if _runtime is None:
        with _runtime_lock:
            if _runtime is None:
                _runtime = Week7ChatRuntime()
    return _runtime


def week7_scenario_options() -> list[dict[str, Any]]:
    return get_week7_runtime().scenario_options()


def run_week7_chat(scenario_id: str, architecture: str) -> dict[str, Any]:
    return get_week7_runtime().run(scenario_id, architecture)