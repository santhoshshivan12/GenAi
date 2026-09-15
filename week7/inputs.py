"""Load the Week 7 golden sets and their local PDF evidence."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from week7.schemas import MigrationScenario


def _normalise(text: str) -> str:
    text = text.replace("\u0000", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _stem(filename: str) -> str:
    return Path(filename).stem.lower().replace(" ", "_")


@dataclass(frozen=True)
class SourcePage:
    source_file: str
    page_number: int
    text: str

    @property
    def chunk_id(self) -> str:
        return f"{_stem(self.source_file)}_p{self.page_number}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "page_number": self.page_number,
            "chunk_id": self.chunk_id,
            "text": self.text,
        }


class DocumentationCorpus:
    def __init__(self, pages: list[SourcePage]) -> None:
        self.pages = pages
        self._by_key = {(page.source_file, page.page_number): page for page in pages}

    @classmethod
    def from_directory(cls, documentation_directory: Path) -> "DocumentationCorpus":
        if not documentation_directory.exists():
            raise FileNotFoundError(f"documentation directory not found: {documentation_directory}")
        pages: list[SourcePage] = []
        for path in sorted(documentation_directory.glob("*.pdf")):
            reader = PdfReader(str(path))
            for page_number, page in enumerate(reader.pages, start=1):
                text = _normalise(page.extract_text() or "")
                if text:
                    pages.append(SourcePage(path.name, page_number, text))
        if not pages:
            raise ValueError(f"no readable PDF pages found under {documentation_directory}")
        return cls(pages)

    def read(self, source_file: str, page_number: int) -> SourcePage | None:
        return self._by_key.get((source_file, page_number))

    def search(
        self,
        query: str,
        *,
        source_files: list[str] | None = None,
        page_numbers: list[int] | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        query_terms = {
            term.lower()
            for term in re.findall(r"[a-zA-Z][a-zA-Z0-9_./-]{2,}", query)
            if term.lower() not in {"what", "which", "how", "does", "between", "from", "with", "the", "and"}
        }
        allowed_files = set(source_files or [])
        allowed_pages = set(page_numbers or [])
        ranked: list[tuple[float, SourcePage]] = []
        for page in self.pages:
            if allowed_files and page.source_file not in allowed_files:
                continue
            if allowed_pages and page.page_number not in allowed_pages:
                continue
            haystack = page.text.lower()
            matches = sum(1 for term in query_terms if term in haystack)
            phrase_bonus = 0.25 if query.strip().lower() in haystack else 0.0
            score = (matches / max(1, len(query_terms))) + phrase_bonus
            if score > 0:
                ranked.append((score, page))
        ranked.sort(key=lambda item: (-item[0], item[1].source_file, item[1].page_number))
        return [
            {
                "source_file": page.source_file,
                "page_number": page.page_number,
                "chunk_id": page.chunk_id,
                "score": round(score, 6),
                "text": page.text,
            }
            for score, page in ranked[: max(1, top_k)]
        ]


# The race intentionally mixes fixed-path migrations with three cases where
# the deprecation result changes the next lookup. These cases come directly
# from the supplied golden sets.
WEEK7_SELECTION: list[tuple[str, str, str, str, dict[str, str] | None]] = [
    (
        "medium",
        "01",
        "deprecation_dependent_assignee",
        "If assignee is deprecated, the replacement assignees field must be looked up.",
        {
            "api_version": "2025-06-01",
            "endpoint": "POST /repos/{owner}/{repo}/issues",
            "parameter": "assignee",
        },
    ),
    (
        "medium",
        "04",
        "deprecation_dependent_visibility_default",
        "The next lookup depends on whether the has_issues parameter is deprecated or only visibility-dependent.",
        {
            "api_version": "2025-06-01",
            "endpoint": "POST /user/repos",
            "parameter": "has_issues",
        },
    ),
    (
        "medium",
        "07",
        "deprecation_dependent_private_visibility",
        "If private is deprecated, the replacement visibility enum must be looked up.",
        {
            "api_version": "2025-06-01",
            "endpoint": "POST /user/repos",
            "parameter": "private",
        },
    ),
    ("hard", "01", "fixed_documentation_path", "Both version pages are known from the scenario metadata.", None),
    ("hard", "03", "fixed_documentation_path", "Both config pages are known from the scenario metadata.", None),
    ("hard", "05", "fixed_documentation_path", "Both Java generator pages are known from the scenario metadata.", None),
    ("hard", "06", "fixed_documentation_path", "The release comparison page is known from the scenario metadata.", None),
    ("hard", "08", "fixed_documentation_path", "The pull-request comparison page is known from the scenario metadata.", None),
    ("hard", "09", "fixed_documentation_path", "The Markdown comparison page is known from the scenario metadata.", None),
    ("hard", "10", "fixed_documentation_path", "Both Python generator pages are known from the scenario metadata.", None),
]


def load_scenarios(input_root: Path, scenario_count: int = 10) -> list[MigrationScenario]:
    golden_directory = input_root / "golden_sets"
    paths = {
        "easy": golden_directory / "gs_easy.json",
        "medium": golden_directory / "gs_medium.json",
        "hard": golden_directory / "gs_hard.json",
    }
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"golden set not found: {missing}")

    cases: dict[tuple[str, str], dict[str, Any]] = {}
    for level, path in paths.items():
        raw_cases = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw_cases, list):
            raise ValueError(f"{path.name} must contain a JSON array")
        for case in raw_cases:
            cases[(level, str(case.get("id")))] = case

    if scenario_count < 1 or scenario_count > len(WEEK7_SELECTION):
        raise ValueError(f"scenario_count must be between 1 and {len(WEEK7_SELECTION)}")

    scenarios: list[MigrationScenario] = []
    for index, (level, case_id, dependency_class, reason, deprecation_check) in enumerate(
        WEEK7_SELECTION[:scenario_count], start=1
    ):
        case = cases.get((level, case_id))
        if case is None:
            raise ValueError(f"selected case not found: {level}-{case_id}")
        scenarios.append(
            MigrationScenario.from_golden_case(
                case,
                f"{level}-{case_id}",
                dependency_class=dependency_class,
                dependency_reason=reason,
                deprecation_check=deprecation_check,
            )
        )
    return scenarios