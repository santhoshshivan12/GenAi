from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from fastapi import UploadFile
from pypdf import PdfReader

from rag.config import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, DEFAULT_SCORE_THRESHOLD
from rag.embeddings import EmbeddingBackend
from rag.env import load_env_file
from rag.models import ChunkRecord, DocumentRecord
from rag.retriever import Retriever
from rag.store import LocalStore
from rag.utils import chunk_text, clean_text, ensure_dirs, snippet, slugify_filename


class RAGService:
    def __init__(self) -> None:
        load_env_file()
        self.store = LocalStore()
        self.embeddings = EmbeddingBackend()
        self.retriever = Retriever(self.store, self.embeddings)
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()
        self.openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
        self.openrouter_http_referer = os.getenv("OPENROUTER_HTTP_REFERER", "http://127.0.0.1:8000").strip()
        self.openrouter_title = os.getenv("OPENROUTER_TITLE", "RAG Demo").strip()

        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _write_upload(self, filename: str, content: bytes) -> Path:
        from rag.config import UPLOAD_DIR

        ensure_dirs([UPLOAD_DIR])
        safe_name = f"{uuid4().hex}_{slugify_filename(filename)}{Path(filename).suffix.lower()}"
        path = UPLOAD_DIR / safe_name
        path.write_bytes(content)
        return path

    def _extract_pdf_pages(self, path: Path) -> list[tuple[int, str]]:
        reader = PdfReader(str(path))
        pages: list[tuple[int, str]] = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            text = clean_text(text)
            if text:
                pages.append((index, text))
        return pages

    def _extract_text_file(self, path: Path) -> list[tuple[int | None, str]]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        text = clean_text(text)
        return [(None, text)] if text else []

    def ingest_uploads(self, uploads: Iterable[UploadFile]) -> list[dict[str, Any]]:
        stored_documents: list[dict[str, Any]] = []

        for upload in uploads:
            content = upload.file.read()
            stored_path = self._write_upload(upload.filename, content)
            suffix = stored_path.suffix.lower()
            document_id = uuid4().hex
            created_at = self._timestamp()

            if suffix == ".pdf":
                pages = self._extract_pdf_pages(stored_path)
                raw_segments = pages
                source_type = "pdf"
                page_count = len(pages)
            else:
                raw_segments = self._extract_text_file(stored_path)
                source_type = "text"
                page_count = None

            chunk_payloads: list[ChunkRecord] = []
            chunk_index = 0
            text_length = 0

            for page_number, segment_text in raw_segments:
                pieces = chunk_text(segment_text, DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP)
                text_length += len(segment_text)
                for piece in pieces:
                    chunk_id = uuid4().hex
                    embedding = self.embeddings.encode([piece])[0]
                    chunk_payloads.append(
                        ChunkRecord(
                            id=chunk_id,
                            document_id=document_id,
                            document_filename=upload.filename,
                            chunk_index=chunk_index,
                            page_number=page_number,
                            text=piece,
                            embedding=embedding,
                            created_at=created_at,
                        )
                    )
                    chunk_index += 1

            document = DocumentRecord(
                id=document_id,
                filename=upload.filename,
                source_type=source_type,
                stored_path=str(stored_path),
                created_at=created_at,
                chunk_count=len(chunk_payloads),
                page_count=page_count,
                text_length=text_length,
            )
            self.store.add_document(document)
            self.store.add_chunks(chunk_payloads)
            self.retriever.add_chunks([item.to_dict() for item in chunk_payloads])

            stored_documents.append(
                {
                    "document": document.to_dict(),
                    "chunks": [item.to_dict() for item in chunk_payloads],
                }
            )

        return stored_documents

    def delete_document(self, document_id: str) -> dict[str, Any]:
        document = self.store.get_document(document_id)
        if document is None:
            return {"deleted": False, "reason": "document_not_found"}

        self.retriever.delete_document(document_id)
        _, removed_chunks = self.store.delete_document(document_id)
        return {
            "deleted": True,
            "document_id": document_id,
            "removed_chunks": len(removed_chunks),
        }

    def delete_chunk(self, chunk_id: str) -> dict[str, Any]:
        chunk = self.store.get_chunk(chunk_id)
        if chunk is None:
            return {"deleted": False, "reason": "chunk_not_found"}

        self.retriever.delete_chunks([chunk_id])
        removed = self.store.delete_chunk(chunk_id)
        return {
            "deleted": removed is not None,
            "chunk_id": chunk_id,
            "document_id": chunk.document_id if removed is not None else None,
        }

    def answer(self, question: str, top_k: int = 4, debug: bool = False) -> dict[str, Any]:
        return self._answer_one(question, top_k=top_k, debug=debug)

    def answer_batch(self, questions: list[str], top_k: int = 4, debug: bool = False) -> dict[str, Any]:
        results = [self._answer_one(question, top_k=top_k, debug=debug) for question in questions if question.strip()]
        return {
            "count": len(results),
            "results": results,
        }

    def _answer_one(self, question: str, top_k: int = 4, debug: bool = False) -> dict[str, Any]:
        hits = self.retriever.search(question, top_k=top_k)
        if not hits:
            payload = {
                "question": question,
                "answer": "I do not know. No documents have been ingested yet.",
                "sources": [],
                "source_pages": [],
                "context": [],
                "chunks": [],
                "used_llm": False,
            }
            if debug:
                payload["debug"] = {
                    "reason": "no_documents",
                    "top_k": top_k,
                    "hit_count": 0,
                }
            return payload

        best_score = hits[0]["score"]
        if best_score < DEFAULT_SCORE_THRESHOLD:
            payload = {
                "question": question,
                "answer": "I do not know. I could not find a relevant chunk in the indexed documents.",
                "sources": hits,
                "source_pages": [],
                "context": [],
                "chunks": hits,
                "used_llm": False,
            }
            if debug:
                payload["debug"] = {
                    "reason": "score_below_threshold",
                    "threshold": DEFAULT_SCORE_THRESHOLD,
                    "best_score": best_score,
                    "top_k": top_k,
                    "top_hits": self._debug_hits(hits),
                }
            return payload

        sources = self._build_sources(hits)
        context_blocks = self._build_context_blocks(hits)
        source_pages = self._extract_source_pages(hits)
        llm_answer = self._generate_answer_with_llm(question, context_blocks)
        used_llm = llm_answer is not None
        answer_text = llm_answer
        if answer_text is None:
            answer_text = self._build_local_answer(question, hits)

        payload = {
            "question": question,
            "answer": answer_text,
            "sources": sources,
            "source_pages": source_pages,
            "context": context_blocks,
            "chunks": hits,
            "used_llm": used_llm,
        }
        if debug:
            payload["debug"] = {
                "threshold": DEFAULT_SCORE_THRESHOLD,
                "best_score": best_score,
                "top_k": top_k,
                "top_hits": self._debug_hits(hits),
                "context_text": self._build_context(context_blocks),
            }
        return payload

    def _debug_hits(self, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "document_filename": hit["document_filename"],
                "page_number": hit["page_number"],
                "chunk_index": hit["chunk_index"],
                "score": round(hit["score"], 4),
                "text_preview": snippet(hit["text"], 200),
                "chunk_id": hit["id"],
            }
            for hit in hits
        ]

    def _build_sources(self, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sources = []
        seen = set()
        for hit in hits:
            key = (hit["document_id"], hit["chunk_index"])
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "document_id": hit["document_id"],
                    "filename": hit["document_filename"],
                    "page_number": hit["page_number"],
                    "chunk_index": hit["chunk_index"],
                    "score": round(hit["score"], 4),
                    "preview": snippet(hit["text"]),
                }
            )
        return sources

    def _extract_source_pages(self, hits: list[dict[str, Any]]) -> list[int]:
        pages = []
        seen = set()
        for hit in hits:
            page_number = hit["page_number"]
            if page_number is None or page_number in seen:
                continue
            seen.add(page_number)
            pages.append(page_number)
        return pages

    def _build_context_blocks(self, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        blocks = []
        for index, hit in enumerate(hits, start=1):
            blocks.append(
                {
                    "ref": index,
                    "document_filename": hit["document_filename"],
                    "page_number": hit["page_number"],
                    "chunk_index": hit["chunk_index"],
                    "text": hit["text"],
                }
            )
        return blocks

    def _build_context(self, context_blocks: list[dict[str, Any]]) -> str:
        lines = []
        for block in context_blocks:
            page_part = "" if block["page_number"] is None else f", page {block['page_number']}"
            lines.append(
                f"[{block['ref']}] {block['document_filename']}{page_part}, chunk {block['chunk_index']}\n"
                f"{block['text']}"
            )
        return "\n\n".join(lines)

    def _build_local_answer(self, question: str, hits: list[dict[str, Any]]) -> str:
        lines = [
            f"Question: {question}",
            "",
            "Grounded answer:",
        ]
        for hit in hits:
            page_part = "" if hit["page_number"] is None else f", page {hit['page_number']}"
            lines.append(
                f"- {snippet(hit['text'], 280)} "
                f"[source: {hit['document_filename']}{page_part}, chunk {hit['chunk_index']}, score {hit['score']:.3f}]"
            )
        lines.append("")
        lines.append("If you want, I can narrow this to a specific document or page.")
        return "\n".join(lines)

    def _generate_answer_with_llm(self, question: str, context_blocks: list[dict[str, Any]]) -> str | None:
        provider_key = self.openrouter_api_key or self.openai_api_key
        if not provider_key:
            return None

        context = self._build_context(context_blocks)
        if self.openrouter_api_key:
            model = self.openrouter_model
            base_url = self.openrouter_base_url
        else:
            model = self.openai_model
            base_url = self.openai_base_url

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You answer strictly from the provided context. "
                        "If the context does not contain the answer, say you do not know. "
                        "Return a concise grounded answer. "
                        "Mention page numbers when possible."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Question: {question}\n\n"
                        f"Context:\n{context}\n\n"
                        "Write a concise answer grounded in the context only."
                    ),
                },
            ],
            "temperature": 0.2,
        }

        request = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {provider_key}",
                **(
                    {
                        "HTTP-Referer": self.openrouter_http_referer,
                        "X-Title": self.openrouter_title,
                        "X-OpenRouter-Metadata": "enabled",
                    }
                    if self.openrouter_api_key
                    else {}
                ),
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
            choices = body.get("choices", [])
            if not choices:
                return None
            message = choices[0].get("message", {})
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError):
            return None
        return None

    def documents_payload(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.store.list_documents()]

    def chunks_payload(self, limit: int | None = None) -> list[dict[str, Any]]:
        chunks = self.store.list_chunks()
        if limit is not None:
            chunks = chunks[-limit:]
        return [item.to_dict() for item in chunks]

    def document_payload(self, document_id: str) -> dict[str, Any] | None:
        document = self.store.get_document(document_id)
        if document is None:
            return None
        chunks = self.store.get_chunks_for_document(document_id)
        return {
            "document": document.to_dict(),
            "chunks": [item.to_dict() for item in chunks],
        }

    def document_debug(self, document_id: str) -> dict[str, Any] | None:
        document = self.store.get_document(document_id)
        if document is None:
            return None

        raw_pages: list[dict[str, Any]] = []
        path = Path(document.stored_path)
        if path.exists():
            if document.source_type == "pdf":
                for page_number, text in self._extract_pdf_pages(path):
                    raw_pages.append(
                        {
                            "page_number": page_number,
                            "text": text,
                            "preview": snippet(text, 400),
                        }
                    )
            else:
                for page_number, text in self._extract_text_file(path):
                    raw_pages.append(
                        {
                            "page_number": page_number,
                            "text": text,
                            "preview": snippet(text, 400),
                        }
                    )

        return {
            "document": document.to_dict(),
            "raw_pages": raw_pages,
            "chunks": [item.to_dict() for item in self.store.get_chunks_for_document(document_id)],
        }

    def stats(self) -> dict[str, Any]:
        return self.store.stats()
