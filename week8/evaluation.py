"""Run, score, and report the Week 8 trajectory experiment."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from week7.architectures import ReActAgent
from week7.inputs import DocumentationCorpus, load_scenarios
from week7.schemas import BenchmarkLimits, RunResult, SchemaError
from week7.tools import ToolRegistry, _validate_schema
from week8.expected import ALTERNATE_PATH_CASES, EXPECTED_TRAJECTORIES, Path as ExpectedPath, path_matches
from week8.mitigation import MITIGATION_EVENT_NAME, ReplanningReActAgent


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_ROOT = PROJECT_ROOT / "input_files 1" / "input_files"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "week8" / "results"
FAILURE_MODES = (
    "wrong_tool_choice",
    "invalid_arguments",
    "missing_required_step",
    "unnecessary_steps",
    "repeated_tool_loop",
    "premature_termination",
    "outcome_failure",
    "right_answer_wrong_path",
)


def _percent(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 2) if denominator else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def _event_arguments(detail: str) -> dict[str, Any]:
    marker = "; args="
    if marker not in detail:
        return {}
    try:
        value = json.loads(detail.split(marker, 1)[1])
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def extract_calls(result: RunResult) -> list[tuple[str, dict[str, Any]]]:
    return [
        (event.name, _event_arguments(event.detail))
        for event in result.events
        if event.event_type == "tool_call"
    ]


def _lcs_length(left: list[str], right: list[str]) -> int:
    row = [0] * (len(right) + 1)
    for left_value in left:
        previous = 0
        for index, right_value in enumerate(right, start=1):
            saved = row[index]
            if left_value == right_value:
                row[index] = previous + 1
            else:
                row[index] = max(row[index], row[index - 1])
            previous = saved
    return row[-1]


def _best_expected_path(calls: list[tuple[str, dict[str, Any]]], paths: frozenset[ExpectedPath]) -> ExpectedPath:
    actual_names = [name for name, _ in calls]
    return max(
        paths,
        key=lambda path: (
            _lcs_length(actual_names, [item.name for item in path]),
            -abs(len(calls) - len(path)),
        ),
    )


def semantic_arguments_valid(
    name: str,
    arguments: dict[str, Any],
    registry: ToolRegistry,
) -> tuple[bool, str]:
    """Validate syntax plus real corpus/version/endpoint semantics."""

    definition = registry.definitions.get(name)
    if definition is None:
        return False, "unknown tool"
    try:
        _validate_schema(arguments, definition.input_schema)
    except SchemaError as exc:
        return False, str(exc)

    if name == "inspect_source":
        if registry.corpus.read(arguments["source_file"], arguments["page_number"]) is None:
            return False, "source/page does not exist"
    elif name == "search_documentation":
        files = arguments.get("source_files", [])
        pages = arguments.get("page_numbers", [])
        corpus_files = {page.source_file for page in registry.corpus.pages}
        if any(source_file not in corpus_files for source_file in files):
            return False, "search source file does not exist"
        if pages:
            candidates = registry.corpus.pages
            if files:
                candidates = [page for page in candidates if page.source_file in files]
            real_pages = {page.page_number for page in candidates}
            if any(page_number not in real_pages for page_number in pages):
                return False, "search page does not exist in selected sources"
    elif name == "check_deprecation":
        known = {
            tuple(check[key] for key in ("api_version", "endpoint", "parameter"))
            for scenario in registry.scenarios.values()
            if (check := scenario.deprecation_check) is not None
        }
        candidate = tuple(arguments[key] for key in ("api_version", "endpoint", "parameter"))
        if candidate not in known:
            return False, "version/endpoint/parameter combination is not in the evaluated API"
    return True, "valid"


def _repeated_exact_call(calls: list[tuple[str, dict[str, Any]]]) -> bool:
    seen: set[str] = set()
    for name, arguments in calls:
        fingerprint = f"{name}:{json.dumps(arguments, sort_keys=True)}"
        if fingerprint in seen:
            return True
        seen.add(fingerprint)
    return False


def score_run(result: RunResult, registry: ToolRegistry) -> dict[str, Any]:
    paths = EXPECTED_TRAJECTORIES[result.scenario_id]
    calls = extract_calls(result)
    best_path = _best_expected_path(calls, paths)
    actual_names = [name for name, _ in calls]
    expected_names = [item.name for item in best_path]
    lcs = _lcs_length(actual_names, expected_names)
    argument_checks = [semantic_arguments_valid(name, arguments, registry) for name, arguments in calls]
    arguments_valid = all(valid for valid, _ in argument_checks)
    sequence_valid = any(path_matches(calls, path) for path in paths)
    trajectory_pass = sequence_valid and arguments_valid
    minimum_steps = min(len(path) for path in paths)
    expected_name_set = {item.name for path in paths for item in path}
    missing_step = lcs < minimum_steps
    unnecessary = len(calls) > minimum_steps
    modes = {
        "wrong_tool_choice": any(name not in expected_name_set for name in actual_names),
        "invalid_arguments": not arguments_valid,
        "missing_required_step": missing_step,
        "unnecessary_steps": unnecessary,
        "repeated_tool_loop": _repeated_exact_call(calls),
        "premature_termination": result.aborted or (len(calls) < minimum_steps and not result.success),
        "outcome_failure": not result.success,
        "right_answer_wrong_path": result.success and not trajectory_pass,
    }
    return {
        "scenario_id": result.scenario_id,
        "outcome_pass": result.success,
        "trajectory_pass": trajectory_pass,
        "sequence_valid": sequence_valid,
        "arguments_valid": arguments_valid,
        "argument_checks": [
            {"tool": call[0], "valid": check[0], "reason": check[1]}
            for call, check in zip(calls, argument_checks)
        ],
        "actual_trajectory": [{"tool": name, "arguments": arguments} for name, arguments in calls],
        "accepted_path_count": len(paths),
        "alternate_paths_allowed": result.scenario_id in ALTERNATE_PATH_CASES,
        "actual_steps": len(calls),
        "optimal_steps": minimum_steps,
        "step_efficiency_taken_over_needed": round(len(calls) / minimum_steps, 4),
        "tool_choice_matches": lcs,
        "tool_choice_denominator": max(len(calls), minimum_steps),
        "estimated_cost_usd": result.estimated_cost_usd,
        "latency_ms": result.latency_ms,
        "total_tokens": result.input_tokens + result.output_tokens,
        "failure_modes": [name for name, present in modes.items() if present],
    }


def summarise(scored: list[dict[str, Any]]) -> dict[str, Any]:
    outcome_passes = sum(item["outcome_pass"] for item in scored)
    trajectory_passes = sum(item["trajectory_pass"] for item in scored)
    tool_matches = sum(item["tool_choice_matches"] for item in scored)
    tool_denominator = sum(item["tool_choice_denominator"] for item in scored)
    valid_arguments = sum(
        check["valid"] for item in scored for check in item["argument_checks"]
    )
    argument_count = sum(len(item["argument_checks"]) for item in scored)
    costs = [item["estimated_cost_usd"] for item in scored]
    modes = Counter(mode for item in scored for mode in item["failure_modes"])
    return {
        "case_count": len(scored),
        "outcome_pass_rate_pct": _percent(outcome_passes, len(scored)),
        "trajectory_pass_rate_pct": _percent(trajectory_passes, len(scored)),
        "outcome_vs_trajectory_gap_percentage_points": round(
            _percent(outcome_passes, len(scored)) - _percent(trajectory_passes, len(scored)), 2
        ),
        "tool_choice_accuracy_pct": _percent(tool_matches, tool_denominator),
        "argument_validity_rate_pct": _percent(valid_arguments, argument_count),
        "step_efficiency_taken_over_needed": round(
            sum(item["step_efficiency_taken_over_needed"] for item in scored) / len(scored), 4
        ) if scored else 0.0,
        "cost_per_question_p50_usd": round(_percentile(costs, 50), 8),
        "cost_per_question_max_usd": round(max(costs), 8) if costs else 0.0,
        "latency_p50_ms": round(_percentile([item["latency_ms"] for item in scored], 50), 4),
        "tokens_p50": round(_percentile([item["total_tokens"] for item in scored], 50), 2),
        "failure_mode_counts": {mode: modes.get(mode, 0) for mode in FAILURE_MODES},
    }


def _mitigation_price(results: list[RunResult]) -> dict[str, Any]:
    overhead = [
        sum(event.output_tokens for event in result.events if event.name == MITIGATION_EVENT_NAME)
        for result in results
    ]
    return {
        "measure": "added re-planning reasoning tokens per question",
        "p50_tokens": round(float(median(overhead)), 2) if overhead else 0.0,
        "max_tokens": max(overhead, default=0),
    }


def _trace_text(item: dict[str, Any]) -> str:
    return " -> ".join(call["tool"] for call in item["actual_trajectory"])


def render_report(report: dict[str, Any]) -> str:
    before = report["before"]["metrics"]
    after = report["after"]["metrics"]
    example = report["right_answer_wrong_path_example"]
    price = report["mitigation"]["price"]
    lines = [
        "# Week 8 Trajectory Evaluation",
        "",
        f"Run timestamp (UTC): `{report['metadata']['run_timestamp_utc']}`  ",
        "Cases: `10` Week 7 documentation migrations  ",
        "Single mitigation: `re-planning exact source/page pairs after search`",
        "",
        "## Flow",
        "",
        "`question -> agent tool calls -> trajectory capture -> path/argument scoring -> gap -> one mitigation -> re-run -> regression check`",
        "",
        "## Required trajectory metrics",
        "",
        "| Metric | Before | After |",
        "|---|---:|---:|",
        f"| Tool-choice accuracy | {before['tool_choice_accuracy_pct']:.2f}% | {after['tool_choice_accuracy_pct']:.2f}% |",
        f"| Argument validity | {before['argument_validity_rate_pct']:.2f}% | {after['argument_validity_rate_pct']:.2f}% |",
        f"| Step efficiency (taken / needed; 1.0 is optimal) | {before['step_efficiency_taken_over_needed']:.4f} | {after['step_efficiency_taken_over_needed']:.4f} |",
        f"| Cost/question p50 | ${before['cost_per_question_p50_usd']:.8f} | ${after['cost_per_question_p50_usd']:.8f} |",
        f"| Cost/question max | ${before['cost_per_question_max_usd']:.8f} | ${after['cost_per_question_max_usd']:.8f} |",
        f"| Outcome pass rate | {before['outcome_pass_rate_pct']:.2f}% | {after['outcome_pass_rate_pct']:.2f}% |",
        f"| Trajectory pass rate | {before['trajectory_pass_rate_pct']:.2f}% | {after['trajectory_pass_rate_pct']:.2f}% |",
        f"| Outcome - trajectory gap | {before['outcome_vs_trajectory_gap_percentage_points']:.2f} pp | {after['outcome_vs_trajectory_gap_percentage_points']:.2f} pp |",
        "",
        "## Right answer, wrong path",
        "",
        f"`{example['scenario_id']}` passed the outcome eval but failed the trajectory eval.",
        f"Observed path: `{example['trace']}`.",
        f"It took {example['actual_steps']} tool steps; the accepted path needs {example['optimal_steps']}.",
        "",
        "## Exactly one mitigation",
        "",
        f"Top mode `unnecessary_steps`: **{report['mitigation']['before_count']} -> {report['mitigation']['after_count']}** cases.",
        f"Measured price: **{price['p50_tokens']:.2f} p50 added tokens/question** (max {price['max_tokens']}).",
        "No other mitigation was applied.",
        "",
        "## Regression matrix",
        "",
        "| Failure mode | Before | After | Delta |",
        "|---|---:|---:|---:|",
    ]
    for row in report["regression"]:
        lines.append(f"| {row['mode']} | {row['before']} | {row['after']} | {row['delta']:+d} |")
    lines.extend([
        "",
        f"Modes that worsened or appeared: {', '.join(report['regression_summary']['worsened_or_new']) or 'none'}.",
        "",
        "## Accepted alternate paths",
        "",
        "The two-document cases `hard-03`, `hard-05`, and `hard-10` accept either source inspection order. All other cases assert one valid tool order.",
        "",
        "Token and cost values use Week 7's transparent offline estimator. Actual provider spend remains $0 because this suite makes no hosted-model call.",
        "",
    ])
    return "\n".join(lines)


def run_trajectory_evaluation(
    input_root: Path = DEFAULT_INPUT_ROOT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    limits: BenchmarkLimits | None = None,
) -> dict[str, Any]:
    limits = limits or BenchmarkLimits()
    scenarios = load_scenarios(input_root, scenario_count=10)
    expected_ids = set(EXPECTED_TRAJECTORIES)
    actual_ids = {scenario.scenario_id for scenario in scenarios}
    if expected_ids != actual_ids:
        raise AssertionError(f"expected trajectory IDs do not match suite: {expected_ids ^ actual_ids}")

    corpus = DocumentationCorpus.from_directory(input_root / "developer_documentations")
    registry = ToolRegistry(corpus, scenarios)
    before_results = [ReActAgent(registry, limits).run(scenario) for scenario in scenarios]
    after_results = [ReplanningReActAgent(registry, limits).run(scenario) for scenario in scenarios]
    before_cases = [score_run(result, registry) for result in before_results]
    after_cases = [score_run(result, registry) for result in after_results]
    before = summarise(before_cases)
    after = summarise(after_cases)

    false_positives = [item for item in before_cases if item["outcome_pass"] and not item["trajectory_pass"]]
    if not false_positives:
        raise AssertionError("the baseline did not expose a right-answer/wrong-path case")
    # Prefer the largest overrun so the named trace is the clearest example.
    example = max(false_positives, key=lambda item: item["actual_steps"] - item["optimal_steps"])
    regression = [
        {
            "mode": mode,
            "before": before["failure_mode_counts"][mode],
            "after": after["failure_mode_counts"][mode],
            "delta": after["failure_mode_counts"][mode] - before["failure_mode_counts"][mode],
        }
        for mode in FAILURE_MODES
    ]
    report = {
        "metadata": {
            "week": 8,
            "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "case_count": 10,
            "baseline": "week7.architectures.ReActAgent",
            "single_mitigation": "re-planning",
            "alternate_path_cases": sorted(ALTERNATE_PATH_CASES),
        },
        "before": {"metrics": before, "cases": before_cases},
        "after": {"metrics": after, "cases": after_cases},
        "right_answer_wrong_path_example": {
            "scenario_id": example["scenario_id"],
            "trace": _trace_text(example),
            "actual_steps": example["actual_steps"],
            "optimal_steps": example["optimal_steps"],
        },
        "mitigation": {
            "name": "re-planning",
            "target_mode": "unnecessary_steps",
            "before_count": before["failure_mode_counts"]["unnecessary_steps"],
            "after_count": after["failure_mode_counts"]["unnecessary_steps"],
            "price": _mitigation_price(after_results),
        },
        "regression": regression,
        "regression_summary": {
            "worsened_or_new": [row["mode"] for row in regression if row["delta"] > 0],
            "checked_modes": list(FAILURE_MODES),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "trajectory_results.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "trajectory_results.md").write_text(render_report(report), encoding="utf-8")
    return report
