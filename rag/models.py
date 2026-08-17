from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class DocumentRecord:
    id: str
    filename: str
    source_type: str
    stored_path: str
    created_at: str
    chunk_count: int
    page_count: int | None = None
    text_length: int | None = None
    chunk_strategy: str = "fixed_size"
    source_file: str | None = None
    page_id: str | None = None
    sdk_version: str | None = None
    page_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ChunkRecord:
    id: str
    document_id: str
    document_filename: str
    chunk_index: int
    page_number: int | None
    text: str
    embedding: list[float]
    created_at: str
    chunk_strategy: str = "fixed_size"
    word_count: int | None = None
    char_count: int | None = None
    source_file: str | None = None
    page_id: str | None = None
    sdk_version: str | None = None
    page_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


