"""Small, dependency-free structured schemas used by every Week 7 tool.

The project does not require a new runtime dependency for Week 7.  These
schemas intentionally reject unknown fields and invalid primitive types before
any tool implementation is called, which gives the same safety boundary as a
strict Pydantic model or JSON-schema tool definition.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class SchemaError(ValueError):
    """Raised when an input does not satisfy a strict schema."""


def _dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaError(f"{name} must be an object")
    return value


def _string(value: Any, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise SchemaError(f"{name} must be a non-empty string")
    return value


def _integer(value: Any, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise SchemaError(f"{name} must be >= {minimum}")
    return value


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise SchemaError(f"{name} must be a list of non-empty strings")
    return list(value)


@dataclass(frozen=True)
class SourceCitation:
    source_file: str
    page_number: int
    chunk_id: str
    excerpt: str

    @classmethod
    def from_dict(cls, payload: Any) -> "SourceCitation":
        data = _dict(payload, "citation")
        expected = {"source_file", "page_number", "chunk_id", "excerpt"}
        unknown = set(data) - expected
        missing = expected - set(data)
        if unknown:
            raise SchemaError(f"citation contains unknown fields: {sorted(unknown)}")
        if missing:
            raise SchemaError(f"citation is missing fields: {sorted(missing)}")
        return cls(
            source_file=_string(data["source_file"], "citation.source_file"),
            page_number=_integer(data["page_number"], "citation.page_number", minimum=1),
            chunk_id=_string(data["chunk_id"], "citation.chunk_id"),
            excerpt=_string(data["excerpt"], "citation.excerpt"),
        )


@dataclass(frozen=True)
class MigrationOutput:
    answer: str
    steps: list[str]
    citations: list[SourceCitation]

    @classmethod
    def from_dict(cls, payload: Any) -> "MigrationOutput":
        data = _dict(payload, "migration_output")
        expected = {"answer", "steps", "citations"}
        unknown = set(data) - expected
        missing = expected - set(data)
        if unknown:
            raise SchemaError(f"migration_output contains unknown fields: {sorted(unknown)}")
        if missing:
            raise SchemaError(f"migration_output is missing fields: {sorted(missing)}")
        steps = _string_list(data["steps"], "migration_output.steps")
        if len(steps) < 2:
            raise SchemaError("migration_output.steps must contain at least two steps")
        citations_raw = data["citations"]
        if not isinstance(citations_raw, list) or not citations_raw:
            raise SchemaError("migration_output.citations must be a non-empty list")
        return cls(
            answer=_string(data["answer"], "migration_output.answer"),
            steps=steps,
            citations=[SourceCitation.from_dict(item) for item in citations_raw],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MigrationScenario:
    scenario_id: str
    level: str
    question: str
    reference_answer: str
    metadata: dict[str, Any]
    expected_chunk_id: str | None
    source_files: list[str]
    page_numbers: list[int]
    dependency_class: str = "fixed_documentation_path"
    dependency_reason: str = ""
    deprecation_check: dict[str, str] | None = None
    @classmethod
    def from_golden_case(
        cls,
        case: Any,
        scenario_id: str,
        *,
        dependency_class: str = "fixed_documentation_path",
        dependency_reason: str = "",
        deprecation_check: dict[str, str] | None = None,
    ) -> "MigrationScenario":
        data = _dict(case, "golden_case")
        required = {"id", "level", "metadata", "question", "answer", "expected_chunk_id"}
        missing = required - set(data)
        if missing:
            raise SchemaError(f"golden_case is missing fields: {sorted(missing)}")
        metadata = _dict(data["metadata"], "golden_case.metadata")
        target_files = metadata.get("target_file", [])
        pages = metadata.get("page_number", [])
        if isinstance(target_files, str):
            target_files = [target_files]
        if isinstance(pages, int):
            pages = [pages]
        if not isinstance(target_files, list) or not all(isinstance(item, str) for item in target_files):
            raise SchemaError("golden_case.metadata.target_file must be a string or list of strings")
        if not isinstance(pages, list) or not all(isinstance(item, int) and item >= 1 for item in pages):
            raise SchemaError("golden_case.metadata.page_number must be an integer or list of positive integers")
        if len(target_files) != len(pages):
            raise SchemaError("golden_case target_file and page_number lengths must match")
        if not target_files or any(item == "none" for item in target_files):
            raise SchemaError("Week 7 migration scenarios require source documentation")
        return cls(
            scenario_id=scenario_id,
            level=_string(data["level"], "golden_case.level"),
            question=_string(data["question"], "golden_case.question"),
            reference_answer=_string(data["answer"], "golden_case.answer"),
            metadata=dict(metadata),
            expected_chunk_id=data["expected_chunk_id"],
            source_files=list(target_files),
            page_numbers=list(pages),
            dependency_class=dependency_class,
            dependency_reason=dependency_reason,
            deprecation_check=deprecation_check,
        )

    def to_dict(self, *, include_reference: bool = False) -> dict[str, Any]:
        data = {
            "scenario_id": self.scenario_id,
            "level": self.level,
            "question": self.question,
            "metadata": self.metadata,
            "expected_chunk_id": self.expected_chunk_id,
            "source_files": self.source_files,
            "page_numbers": self.page_numbers,
            "dependency_class": self.dependency_class,
            "dependency_reason": self.dependency_reason,
            "deprecation_check": self.deprecation_check,
        }
        if include_reference:
            data["reference_answer"] = self.reference_answer
        return data


@dataclass(frozen=True)
class BenchmarkLimits:
    max_iterations: int = 8
    max_tool_calls: int = 16
    max_input_tokens: int = 12_000
    max_output_tokens: int = 8_000
    max_cost_usd: float = 0.25
    max_latency_seconds: float = 30.0
    p50_target_seconds: float = 2.0
    p99_target_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.max_iterations < 1 or self.max_tool_calls < 1:
            raise ValueError("iteration and tool-call limits must be positive")
        if self.max_input_tokens < 1 or self.max_output_tokens < 1:
            raise ValueError("token limits must be positive")
        if self.max_cost_usd < 0 or self.max_latency_seconds <= 0:
            raise ValueError("cost must be non-negative and latency must be positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ToolEvent:
    event_type: str
    name: str
    timestamp_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunResult:
    architecture: str
    scenario_id: str
    success: bool
    answer: str
    validation: dict[str, Any]
    iterations: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    actual_cost_usd: float
    latency_ms: float
    aborted: bool
    abort_reason: str | None
    events: list[ToolEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["events"] = [event.to_dict() for event in self.events]
        return data
