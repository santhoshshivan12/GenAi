"""The competing Week 7 execution architectures."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any

from week7.limits import CircuitBreaker, CircuitBreakerTriggered
from week7.schemas import BenchmarkLimits, MigrationScenario, RunResult, ToolEvent
from week7.tools import ToolRegistry


MODEL_NAME = "offline-evidence-synthesizer-v1"


def _citation_from_hit(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_file": hit["source_file"],
        "page_number": hit["page_number"],
        "chunk_id": hit["chunk_id"],
        "excerpt": hit["text"][:1200],
    }


def _build_output(
    question: str,
    pages: list[dict[str, Any]],
    deprecation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    citations: list[dict[str, Any]] = []
    evidence: list[str] = []
    for page in pages:
        citation = _citation_from_hit(page)
        citations.append(citation)
        evidence.append(f"[{citation['source_file']} p.{citation['page_number']}] {citation['excerpt']}")

    decision = "No deprecation branch was required; use the versioned evidence directly."
    if deprecation is not None:
        if deprecation.get("deprecated") and deprecation.get("replacement"):
            decision = (
                f"The deprecation check found {deprecation['parameter']} deprecated in "
                f"{deprecation['api_version']}; follow-up lookup uses replacement "
                f"{deprecation['replacement']}."
            )
        else:
            decision = (
                f"The deprecation check found no replacement for {deprecation['parameter']}; "
                "follow-up lookup uses the version-specific behavior."
            )

    answer = (
        f"Migration request: {question}\n\n"
        "Apply the migration by identifying the version-specific behavior, updating the client/configuration "
        "to the newer form, and verifying the generated request or client output against the source evidence.\n\n"
        f"Path decision: {decision}\n\n"
        "Evidence:\n" + "\n".join(evidence)
    )
    steps = [
        "Identify the old and new behavior from the versioned reference pages.",
        "Inspect the cited source pages and determine whether a deprecation-dependent branch is present.",
        "Update the request, generator configuration, or ignore rules to the documented newer form.",
        "Run a focused verification using the cited pages and retain the migration evidence.",
    ]
    if deprecation is not None:
        steps[2] = "Use the deprecation result to look up the replacement or version-specific behavior before updating the configuration."
    return {"answer": answer, "steps": steps, "citations": citations}


def _has_deprecation_signal(pages: list[dict[str, Any]]) -> bool:
    text = " ".join(str(page.get("text", "")) for page in pages).lower()
    return "deprecated" in text or "supersedes" in text


def _same_page(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return left.get("source_file") == right.get("source_file") and left.get("page_number") == right.get("page_number")


def _apply_deprecation_branch(
    scenario: MigrationScenario,
    pages: list[dict[str, Any]],
    session: "ToolSession",
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Use step-two evidence to decide whether step three needs a deprecation lookup."""
    if not scenario.deprecation_check or not _has_deprecation_signal(pages):
        return pages, None

    deprecation = session.call("check_deprecation", scenario.deprecation_check)
    replacement = deprecation.get("replacement")
    branch_query = scenario.question
    if replacement:
        branch_query += f" replacement {replacement}"
    else:
        branch_query += " version-specific behavior"

    follow_up = session.call(
        "search_documentation",
        {
            "query": branch_query,
            "source_files": scenario.source_files,
            "page_numbers": scenario.page_numbers,
            "top_k": 3,
        },
    )
    for hit in follow_up.get("hits", []):
        if any(_same_page(hit, existing) for existing in pages):
            continue
        inspected = session.call(
            "inspect_source",
            {"source_file": hit["source_file"], "page_number": hit["page_number"]},
        )
        if inspected.get("found"):
            pages.append(inspected)
    return pages, deprecation


class ToolSession:
    def __init__(self, registry: ToolRegistry, breaker: CircuitBreaker, events: list[ToolEvent]) -> None:
        self.registry = registry
        self.breaker = breaker
        self.events = events

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter_ns()
        self.breaker.before_tool_call()
        result = self.registry.execute(name, arguments)
        event = self.breaker.record_tool_call(arguments, result, name)
        event.timestamp_ms = (time.perf_counter_ns() - self.breaker.started_ns) / 1_000_000
        safe_args = {key: value for key, value in arguments.items() if key not in {"text", "excerpt"}}
        event.detail = (
            f"duration_ms={(time.perf_counter_ns() - started) / 1_000_000:.3f}; "
            f"args={json.dumps(safe_args, ensure_ascii=False)}"
        )
        self.events.append(event)
        return result


class ArchitectureRunner(ABC):
    name = "base"

    def __init__(self, registry: ToolRegistry, limits: BenchmarkLimits) -> None:
        self.registry = registry
        self.limits = limits

    @abstractmethod
    def run(self, scenario: MigrationScenario) -> RunResult:
        raise NotImplementedError

    def _result(
        self,
        scenario: MigrationScenario,
        breaker: CircuitBreaker,
        events: list[ToolEvent],
        answer: str,
        validation: dict[str, Any],
    ) -> RunResult:
        return RunResult(
            architecture=self.name,
            scenario_id=scenario.scenario_id,
            success=bool(validation.get("valid", False)) and breaker.abort_reason is None,
            answer=answer,
            validation=validation,
            iterations=breaker.iterations,
            tool_calls=breaker.tool_calls,
            input_tokens=breaker.input_tokens,
            output_tokens=breaker.output_tokens,
            estimated_cost_usd=breaker.estimated_cost_usd,
            actual_cost_usd=breaker.actual_cost_usd,
            latency_ms=breaker.elapsed_seconds * 1000,
            aborted=breaker.abort_reason is not None,
            abort_reason=breaker.abort_reason,
            events=events,
        )

    def _aborted_result(
        self,
        scenario: MigrationScenario,
        breaker: CircuitBreaker,
        events: list[ToolEvent],
        error: str,
    ) -> RunResult:
        return self._result(scenario, breaker, events, "", {"valid": False, "reason": error})


class DeterministicWorkflow(ArchitectureRunner):
    """Fixed stages: search -> inspect -> optional deprecation branch -> output validation."""

    name = "deterministic_workflow"

    def run(self, scenario: MigrationScenario) -> RunResult:
        breaker = CircuitBreaker(self.limits)
        breaker.start()
        events: list[ToolEvent] = []
        try:
            breaker.begin_iteration()
            session = ToolSession(self.registry, breaker, events)
            search = session.call(
                "search_documentation",
                {
                    "query": scenario.question,
                    "source_files": scenario.source_files,
                    "page_numbers": scenario.page_numbers,
                    "top_k": 5,
                },
            )
            pages: list[dict[str, Any]] = []
            for source_file, page_number in zip(scenario.source_files, scenario.page_numbers):
                inspected = session.call(
                    "inspect_source", {"source_file": source_file, "page_number": page_number}
                )
                if inspected.get("found"):
                    pages.append(inspected)
            if not pages:
                pages = list(search.get("hits", []))
            pages, deprecation = _apply_deprecation_branch(scenario, pages, session)
            output = _build_output(scenario.question, pages, deprecation)
            validation = self.registry.validate_output(scenario.scenario_id, output)
            return self._result(scenario, breaker, events, output["answer"], validation)
        except CircuitBreakerTriggered as exc:
            return self._aborted_result(scenario, breaker, events, exc.reason)
        except Exception as exc:
            breaker.abort_reason = f"execution error: {exc}"
            return self._aborted_result(scenario, breaker, events, breaker.abort_reason)


class ReActAgent(ArchitectureRunner):
    """Adaptive bounded ReAct policy using the same tools and output model."""

    name = "react_agent"

    def run(self, scenario: MigrationScenario) -> RunResult:
        breaker = CircuitBreaker(self.limits)
        breaker.start()
        events: list[ToolEvent] = []
        try:
            session = ToolSession(self.registry, breaker, events)
            pages: list[dict[str, Any]] = []
            validation: dict[str, Any] = {"valid": False, "reason": "not attempted"}
            answer = ""
            dependency_checked = False
            for attempt in range(2):
                breaker.begin_iteration()
                query = scenario.question if attempt == 0 else scenario.question + " migration compatibility defaults comparison"
                events.append(breaker.record_reasoning(f"Thought {attempt + 1}: search, inspect, then choose the next tool."))
                search = session.call(
                    "search_documentation",
                    {
                        "query": query,
                        "source_files": scenario.source_files,
                        "page_numbers": scenario.page_numbers,
                        "top_k": 3,
                    },
                )
                observed = search.get("hits", [])
                for hit in observed:
                    if any(_same_page(hit, existing) for existing in pages):
                        continue
                    inspected = session.call(
                        "inspect_source",
                        {"source_file": hit["source_file"], "page_number": hit["page_number"]},
                    )
                    if inspected.get("found"):
                        pages.append(inspected)
                if attempt == 1:
                    for source_file, page_number in zip(scenario.source_files, scenario.page_numbers):
                        if not any(
                            item.get("source_file") == source_file and item.get("page_number") == page_number
                            for item in pages
                        ):
                            inspected = session.call(
                                "inspect_source", {"source_file": source_file, "page_number": page_number}
                            )
                            if inspected.get("found"):
                                pages.append(inspected)
                deprecation = None
                if not dependency_checked:
                    pages, deprecation = _apply_deprecation_branch(scenario, pages, session)
                    dependency_checked = True
                output = _build_output(scenario.question, pages, deprecation)
                answer = output["answer"]
                validation = self.registry.validate_output(scenario.scenario_id, output)
                if validation.get("valid"):
                    break
                events.append(breaker.record_reasoning("Validation failed; refine retrieval before stopping."))
            return self._result(scenario, breaker, events, answer, validation)
        except CircuitBreakerTriggered as exc:
            return self._aborted_result(scenario, breaker, events, exc.reason)
        except Exception as exc:
            breaker.abort_reason = f"execution error: {exc}"
            return self._aborted_result(scenario, breaker, events, breaker.abort_reason)