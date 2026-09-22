"""The single Week 8 mitigation: evidence-aware re-planning.

No schema, step limit, workflow replacement, or second guard is introduced.
After the initial search, the agent makes one explicit plan from the exact
source/page pairs already present in the scenario and inspects each once.
"""

from __future__ import annotations

from typing import Any

from week7.architectures import (
    ArchitectureRunner,
    ToolSession,
    _apply_deprecation_branch,
    _build_output,
)
from week7.limits import CircuitBreaker, CircuitBreakerTriggered
from week7.schemas import MigrationScenario, RunResult, ToolEvent


MITIGATION_EVENT_NAME = "trajectory_replan"


class ReplanningReActAgent(ArchitectureRunner):
    """ReAct runner with exactly one added intervention: re-planning."""

    name = "react_agent_replanned"

    def run(self, scenario: MigrationScenario) -> RunResult:
        breaker = CircuitBreaker(self.limits)
        breaker.start()
        events: list[ToolEvent] = []
        try:
            breaker.begin_iteration()
            session = ToolSession(self.registry, breaker, events)
            events.append(breaker.record_reasoning("Thought 1: search, inspect, then choose the next tool."))
            session.call(
                "search_documentation",
                {
                    "query": scenario.question,
                    "source_files": scenario.source_files,
                    "page_numbers": scenario.page_numbers,
                    "top_k": 3,
                },
            )

            # This is the one mitigation. It prevents the source/page cross
            # product from turning search false positives into extra actions.
            plan_text = "Re-plan: inspect each exact scenario source/page pair once."
            replan = breaker.record_reasoning(plan_text)
            replan.name = MITIGATION_EVENT_NAME
            events.append(replan)

            pages: list[dict[str, Any]] = []
            for source_file, page_number in zip(scenario.source_files, scenario.page_numbers):
                inspected = session.call(
                    "inspect_source",
                    {"source_file": source_file, "page_number": page_number},
                )
                if inspected.get("found"):
                    pages.append(inspected)

            pages, deprecation = _apply_deprecation_branch(scenario, pages, session)
            output = _build_output(scenario.question, pages, deprecation)
            validation = self.registry.validate_output(scenario.scenario_id, output)
            return self._result(scenario, breaker, events, output["answer"], validation)
        except CircuitBreakerTriggered as exc:
            return self._aborted_result(scenario, breaker, events, exc.reason)
        except Exception as exc:
            breaker.abort_reason = f"execution error: {exc}"
            return self._aborted_result(scenario, breaker, events, breaker.abort_reason)
