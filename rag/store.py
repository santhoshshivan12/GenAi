from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag.config import CHUNKS_FILE, DATA_DIR, DOCS_FILE
from rag.models import ChunkRecord, DocumentRecord
from rag.utils import ensure_dirs


class LocalStore:
    def __init__(self) -> None:
        ensure_dirs([DATA_DIR])
        self._lock = threading.Lock()
        self._documents = self._load_documents()
        self._chunks = self._load_chunks()

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json(self, path: Path, payload: Any) -> None:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def _load_documents(self) -> list[DocumentRecord]:
        raw = self._read_json(DOCS_FILE, [])
        return [DocumentRecord(**item) for item in raw]

    def _load_chunks(self) -> list[ChunkRecord]:
        raw = self._read_json(CHUNKS_FILE, [])
        return [ChunkRecord(**item) for item in raw]

    def _flush(self) -> None:
        self._write_json(DOCS_FILE, [item.to_dict() for item in self._documents])
        self._write_json(CHUNKS_FILE, [item.to_dict() for item in self._chunks])

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def add_document(self, document: DocumentRecord) -> None:
        with self._lock:
            self._documents.append(document)
            self._flush()

    def add_chunks(self, chunks: list[ChunkRecord]) -> None:
        with self._lock:
            self._chunks.extend(chunks)
            self._flush()

    def delete_document(self, document_id: str) -> tuple[DocumentRecord | None, list[ChunkRecord]]:
        with self._lock:
            document = None
            remaining_documents: list[DocumentRecord] = []
            for item in self._documents:
                if item.id == document_id and document is None:
                    document = item
                else:
                    remaining_documents.append(item)

            removed_chunks = [item for item in self._chunks if item.document_id == document_id]
            self._documents = remaining_documents
            self._chunks = [item for item in self._chunks if item.document_id != document_id]
            if document is not None or removed_chunks:
                self._flush()
            return document, removed_chunks

    def delete_chunk(self, chunk_id: str) -> ChunkRecord | None:
        with self._lock:
            removed = None
            remaining_chunks: list[ChunkRecord] = []
            for item in self._chunks:
                if item.id == chunk_id and removed is None:
                    removed = item
                else:
                    remaining_chunks.append(item)
            if removed is not None:
                self._chunks = remaining_chunks
                self._flush()
            return removed

    def list_documents(self) -> list[DocumentRecord]:
        with self._lock:
            return list(self._documents)

    def list_chunks(self) -> list[ChunkRecord]:
        with self._lock:
            return list(self._chunks)

    def get_document(self, document_id: str) -> DocumentRecord | None:
        with self._lock:
            for item in self._documents:
                if item.id == document_id:
                    return item
        return None

    def get_chunks_for_document(self, document_id: str) -> list[ChunkRecord]:
        with self._lock:
            return [item for item in self._chunks if item.document_id == document_id]

    def get_chunk(self, chunk_id: str) -> ChunkRecord | None:
        with self._lock:
            for item in self._chunks:
                if item.id == chunk_id:
                    return item
        return None

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "documents": len(self._documents),
                "chunks": len(self._chunks),
            }
