"""The ten asserted documentation trajectories used by the Week 8 eval.

Each case contains a *set* of accepted paths.  The three two-document cases
accept either source-inspection order; the other seven cases have one valid
order.  Search text is intentionally not pinned because a focused rewrite is
legitimate, while source/page, endpoint, parameter, and version arguments are
asserted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExpectedCall:
    name: str
    required_arguments: dict[str, Any]

    def __hash__(self) -> int:
        return hash((self.name, repr(sorted(self.required_arguments.items()))))


Path = tuple[ExpectedCall, ...]


def call(name: str, **required_arguments: Any) -> ExpectedCall:
    return ExpectedCall(name, required_arguments)


def fixed_path(source_file: str, page_number: int) -> Path:
    return (
        call("search_documentation", source_files=[source_file], page_numbers=[page_number]),
        call("inspect_source", source_file=source_file, page_number=page_number),
    )


def two_document_paths(first_file: str, first_page: int, second_file: str, second_page: int) -> frozenset[Path]:
    search = call(
        "search_documentation",
        source_files=[first_file, second_file],
        page_numbers=[first_page, second_page],
    )
    first = call("inspect_source", source_file=first_file, page_number=first_page)
    second = call("inspect_source", source_file=second_file, page_number=second_page)
    return frozenset({(search, first, second), (search, second, first)})


def deprecation_path(page_number: int, endpoint: str, parameter: str) -> Path:
    source_file = "github_combined_reference.pdf"
    search = call(
        "search_documentation",
        source_files=[source_file],
        page_numbers=[page_number],
    )
    return (
        search,
        call("inspect_source", source_file=source_file, page_number=page_number),
        call(
            "check_deprecation",
            api_version="2025-06-01",
            endpoint=endpoint,
            parameter=parameter,
        ),
        search,
    )


# All ten cases are enumerated here rather than inferred from the run.  That
# makes a changed agent path fail the eval instead of silently changing truth.
EXPECTED_TRAJECTORIES: dict[str, frozenset[Path]] = {
    "medium-01": frozenset({
        deprecation_path(5, "POST /repos/{owner}/{repo}/issues", "assignee")
    }),
    "medium-04": frozenset({
        deprecation_path(9, "POST /user/repos", "has_issues")
    }),
    "medium-07": frozenset({
        deprecation_path(9, "POST /user/repos", "private")
    }),
    "hard-01": frozenset({fixed_path("github_combined_reference.pdf", 3)}),
    "hard-03": two_document_paths(
        "swagger_v3_reference.pdf", 6, "swagger_v2_reference.pdf", 5
    ),
    "hard-05": two_document_paths(
        "swagger_v3_reference.pdf", 3, "swagger_v2_reference.pdf", 2
    ),
    "hard-06": frozenset({fixed_path("github_combined_reference.pdf", 13)}),
    "hard-08": frozenset({fixed_path("github_combined_reference.pdf", 7)}),
    "hard-09": frozenset({fixed_path("github_combined_reference.pdf", 3)}),
    "hard-10": two_document_paths(
        "swagger_v3_reference.pdf", 4, "swagger_v2_reference.pdf", 3
    ),
}


ALTERNATE_PATH_CASES = frozenset(
    scenario_id for scenario_id, paths in EXPECTED_TRAJECTORIES.items() if len(paths) > 1
)


def arguments_match(actual: dict[str, Any], expected: ExpectedCall) -> bool:
    return expected.name and all(actual.get(key) == value for key, value in expected.required_arguments.items())


def path_matches(actual: list[tuple[str, dict[str, Any]]], expected: Path) -> bool:
    return len(actual) == len(expected) and all(
        name == wanted.name and arguments_match(arguments, wanted)
        for (name, arguments), wanted in zip(actual, expected)
    )
