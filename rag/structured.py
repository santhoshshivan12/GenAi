from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class RAGAnswer:
    answer: str
    confidence: float
    used_sources: list[int]
    knows_answer: bool
    page_numbers: list[int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_rag_answer(payload: dict[str, Any], valid_refs: set[int] | None = None) -> RAGAnswer:
    answer = payload.get("answer")
    confidence = payload.get("confidence")
    used_sources = payload.get("used_sources")
    knows_answer = payload.get("knows_answer")
    page_numbers = payload.get("page_numbers")

    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("answer must be a non-empty string")
    if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
        raise ValueError("confidence must be a number between 0 and 1")
    if not isinstance(used_sources, list) or not all(isinstance(item, int) for item in used_sources):
        raise ValueError("used_sources must be a list of integers")
    if not isinstance(knows_answer, bool):
        raise ValueError("knows_answer must be a boolean")
    if not isinstance(page_numbers, list) or not all(isinstance(item, int) for item in page_numbers):
        raise ValueError("page_numbers must be a list of integers")

    if valid_refs is not None and any(ref not in valid_refs for ref in used_sources):
        raise ValueError("used_sources contains a reference number that is not present in context")
    if knows_answer and not used_sources:
        raise ValueError("used_sources cannot be empty when knows_answer is true")

    return RAGAnswer(
        answer=answer.strip(),
        confidence=float(confidence),
        used_sources=used_sources,
        knows_answer=knows_answer,
        page_numbers=page_numbers,
    )


def parse_rag_answer(raw: str, valid_refs: set[int] | None = None) -> RAGAnswer:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("model response must be a JSON object")
    return validate_rag_answer(data, valid_refs=valid_refs)

