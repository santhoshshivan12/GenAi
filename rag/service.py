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
from rag.prompts import answer_examples, answer_system_prompt, retrieval_system_prompt
from rag.retriever import Retriever
from rag.store import LocalStore
from rag.structured import RAGAnswer, parse_rag_answer
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
        question = question.strip()
        if not question:
            payload = {
                "question": question,
                "answer": "Invalid question.",
                "sources": [],
                "source_pages": [],
                "context": [],
                "chunks": [],
                "used_llm": False,
                "structured_answer": None,
            }
            if debug:
                payload["debug"] = {"reason": "blank_question"}
            return payload

        if len(question) > 2000:
            payload = {
                "question": question,
                "answer": "Invalid question.",
                "sources": [],
                "source_pages": [],
                "context": [],
                "chunks": [],
                "used_llm": False,
                "structured_answer": None,
            }
            if debug:
                payload["debug"] = {"reason": "question_too_long", "max_length": 2000}
            return payload

        retrieval = self._retrieve_hits_for_question(question, top_k=top_k, debug=debug)
        hits = retrieval["hits"]
        if not hits:
            payload = {
                "question": question,
                "answer": "I do not know. No documents have been ingested yet.",
                "sources": [],
                "source_pages": [],
                "context": [],
                "chunks": [],
                "used_llm": False,
                "structured_answer": None,
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
                "structured_answer": None,
            }
            if debug:
                payload["debug"] = {
                    "reason": "score_below_threshold",
                    "threshold": DEFAULT_SCORE_THRESHOLD,
                    "best_score": best_score,
                    "top_k": top_k,
                    "top_hits": self._debug_hits(hits),
                    "retrieval": retrieval,
                }
            return payload

        context_blocks = self._build_context_blocks(hits)
        model_name = self._active_model_name()
        context_text, included_blocks = self._build_context_within_budget(question, context_blocks, model_name)
        included_hits = self._blocks_to_chunk_hits(included_blocks)
        sources = self._build_sources_from_blocks(included_blocks)
        source_pages = self._extract_source_pages_from_blocks(included_blocks)

        structured_answer, structured_debug = self._generate_structured_answer(
            question=question,
            context_blocks=included_blocks,
            context_text=context_text,
            debug=debug,
        )

        if structured_answer is None:
            answer_text = self._build_local_answer(question, included_hits)
            used_llm = False
        else:
            answer_text = structured_answer.answer
            used_llm = True

        payload: dict[str, Any] = {
            "question": question,
            "answer": answer_text,
            "sources": sources,
            "source_pages": source_pages,
            "context": included_blocks,
            "chunks": included_hits,
            "used_llm": used_llm,
            "structured_answer": structured_answer.to_dict() if structured_answer is not None else None,
        }
        if debug:
            payload["debug"] = {
                "threshold": DEFAULT_SCORE_THRESHOLD,
                "best_score": best_score,
                "top_k": top_k,
                "top_hits": self._debug_hits(hits),
                "context_text": context_text,
                "context_budget": self._context_budget_debug(
                    question=question,
                    model=model_name,
                    all_blocks=context_blocks,
                    included_blocks=included_blocks,
                    context_text=context_text,
                ),
                "retrieval": retrieval,
                "structured": structured_debug,
            }
        return payload

    def _retrieve_hits_for_question(self, question: str, top_k: int, debug: bool = False) -> dict[str, Any]:
        provider_key = self.openrouter_api_key or self.openai_api_key
        fallback_hits = self.retriever.search(question, top_k=top_k)
        result: dict[str, Any] = {
            "mode": "fallback",
            "tool_query": question,
            "tool_top_k": top_k,
            "hits": fallback_hits,
        }

        if not provider_key:
            return result

        messages = [
            {"role": "system", "content": retrieval_system_prompt()},
            {"role": "user", "content": question},
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_documents",
                    "description": "Search the ingested documents for relevant chunks.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "top_k": {"type": "integer", "default": top_k},
                        },
                        "required": ["query"],
                    },
                },
            }
        ]

        response = self._call_llm(messages, tools=tools)
        if response is None:
            return result

        message = response.get("choices", [{}])[0].get("message", {})
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return result

        tool_call = tool_calls[0]
        function = tool_call.get("function", {})
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError:
            arguments = {}

        search_query = str(arguments.get("query") or question).strip() or question
        tool_top_k_raw = arguments.get("top_k", top_k)
        try:
            tool_top_k = int(tool_top_k_raw)
        except (TypeError, ValueError):
            tool_top_k = top_k
        tool_top_k = max(1, min(tool_top_k, 10))

        hits = self.retriever.search(search_query, top_k=tool_top_k)
        result.update(
            {
                "mode": "tool_call",
                "tool_query": search_query,
                "tool_top_k": tool_top_k,
                "tool_call_id": tool_call.get("id"),
                "raw_tool_arguments": arguments,
                "hits": hits,
            }
        )
        return result

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

    def _build_sources_from_blocks(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sources = []
        seen = set()
        for block in blocks:
            key = (block["document_id"], block["chunk_index"])
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "document_id": block["document_id"],
                    "filename": block["document_filename"],
                    "page_number": block["page_number"],
                    "chunk_index": block["chunk_index"],
                    "score": round(block["score"], 4),
                    "preview": snippet(block["text"]),
                }
            )
        return sources

    def _extract_source_pages_from_blocks(self, blocks: list[dict[str, Any]]) -> list[int]:
        pages = []
        seen = set()
        for block in blocks:
            page_number = block["page_number"]
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
                    "document_id": hit["document_id"],
                    "document_filename": hit["document_filename"],
                    "page_number": hit["page_number"],
                    "chunk_index": hit["chunk_index"],
                    "text": hit["text"],
                    "score": hit["score"],
                    "chunk_id": hit["id"],
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

    def _generate_structured_answer(
        self,
        question: str,
        context_blocks: list[dict[str, Any]],
        context_text: str,
        debug: bool = False,
        max_retries: int = 2,
    ) -> tuple[RAGAnswer | None, dict[str, Any]]:
        provider_key = self.openrouter_api_key or self.openai_api_key
        if not provider_key:
            return None, {"reason": "no_llm_key"}

        valid_refs = {block["ref"] for block in context_blocks}
        prompt = self._answer_prompt_prefix() + (
            f"Question: {question}\n\n"
            f"<context>\n{context_text}\n</context>\n\n"
            "Return only valid JSON."
        )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Return the answer as valid JSON only."},
        ]

        last_error = ""
        last_usage: dict[str, Any] | None = None
        for attempt in range(max_retries + 1):
            response = self._call_llm(messages)
            if response is None:
                last_error = "LLM request failed"
                break

            last_usage = response.get("usage") or None
            message = response.get("choices", [{}])[0].get("message", {})
            raw_content = message.get("content") or ""
            try:
                parsed = parse_rag_answer(raw_content, valid_refs=valid_refs)
                return parsed, {
                    "attempts": attempt + 1,
                    "raw_json": raw_content,
                    "model": self._active_model_name(),
                    "usage": last_usage,
                }
            except (ValueError, json.JSONDecodeError) as exc:
                last_error = str(exc)
                messages.append({"role": "assistant", "content": raw_content})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your previous response was invalid: {last_error}. "
                            "Return valid JSON only that matches the schema exactly."
                        ),
                    }
                )

        return None, {
            "attempts": max_retries + 1,
            "last_error": last_error or "unknown_error",
            "model": self._active_model_name(),
            "usage": last_usage,
        }

    def _active_model_name(self) -> str:
        return self.openrouter_model if self.openrouter_api_key else self.openai_model

    def _call_llm(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        provider_key = self.openrouter_api_key or self.openai_api_key
        if not provider_key:
            return None

        if self.openrouter_api_key:
            model = self.openrouter_model
            base_url = self.openrouter_base_url
        else:
            model = self.openai_model
            base_url = self.openai_base_url

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
        }
        if tools is not None:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

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
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
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

