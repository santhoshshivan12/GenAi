from __future__ import annotations

import json


import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from fastapi import UploadFile
from pypdf import PdfReader

from rag.config import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, DEFAULT_SCORE_THRESHOLD, TRACE_FILE
from rag.embeddings import EmbeddingBackend
from rag.env import load_env_file
from rag.models import ChunkRecord, DocumentRecord
from rag.prompts import answer_examples, answer_system_prompt, retrieval_system_prompt
from rag.retriever import Retriever
from rag.store import LocalStore
from rag.structured import RAGAnswer, parse_rag_answer
from rag.utils import chunk_text, clean_text, ensure_dirs, snippet, slugify_filename


TRACE_LOGGER = logging.getLogger("rag.trace")


def _write_trace_log(trace: dict[str, Any]) -> None:
    """Append one self-contained request trace to the application trace log."""
    TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(TRACE_FILE, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    TRACE_LOGGER.addHandler(handler)
    TRACE_LOGGER.setLevel(logging.INFO)
    TRACE_LOGGER.propagate = False
    try:
        TRACE_LOGGER.info(json.dumps(trace, ensure_ascii=False))
    finally:
        TRACE_LOGGER.removeHandler(handler)
        handler.close()


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
        self._hybrid_retriever = None

        # Automatically ingest v2 and v3 default documents on startup if store is empty
        self.auto_ingest_default_docs()

    def auto_ingest_default_docs(self, force: bool = False) -> list[dict[str, Any]]:
        import glob
        if not force and len(self.store.list_documents()) > 0:
            return []

        raw_paths = glob.glob("docs/*/*.pdf") + glob.glob("docs/*/*.docx")
        # Normalize paths to prevent duplicate entries from slash / backslash differences
        unique_paths = sorted(list({str(Path(p).resolve()): str(Path(p)) for p in raw_paths}.values()))
        if unique_paths:
            print(f"Auto-ingesting default SDK v2 & v3 documents: {unique_paths}...")
            return self.ingest_documents_from_paths(unique_paths, chunk_strategy="structure_aware")
        return []

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _write_upload(self, filename: str, content: bytes) -> Path:
        from rag.config import UPLOAD_DIR

        ensure_dirs([UPLOAD_DIR])
        safe_name = f"{uuid4().hex}_{slugify_filename(filename)}{Path(filename).suffix.lower()}"
        path = UPLOAD_DIR / safe_name
        path.write_bytes(content)
        return path

    def _infer_metadata(self, filename: str, text: str) -> dict[str, str]:
        stem = Path(filename).stem.lower()
        text_lower = text.lower()

        # sdk_version
        if "_v2" in stem or "v2" in stem:
            sdk_version = "v2"
        elif "_v3" in stem or "v3" in stem:
            sdk_version = "v3"
        else:
            sdk_version = "v3"

        # page_type
        if "changelog" in stem or "changelog" in text_lower:
            page_type = "changelog"
        elif "guide" in text_lower or "guide" in stem or "auth" in stem or "errors" in stem:
            page_type = "guide"
        else:
            page_type = "reference"

        page_id = stem
        source_file = filename

        return {
            "source_file": source_file,
            "page_id": page_id,
            "sdk_version": sdk_version,
            "page_type": page_type,
        }

    def _extract_docx_markdown(self, path: Path) -> str:
        import zipfile
        import xml.etree.ElementTree as ET

        W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        KNOWN_SECTIONS = {
            "overview", "parameters", "retry parameters", "configuration",
            "configuration parameters", "example", "return value", "retry behavior",
            "security", "compatibility", "request timeouts", "version 3.0.0",
            "breaking changes", "improvements", "migration example", "version metadata",
            "error codes", "common errors", "error handling", "features"
        }

        try:
            with zipfile.ZipFile(path) as z:
                xml_content = z.read("word/document.xml")
                tree = ET.fromstring(xml_content)
                body = tree.find(f"{W_NS}body")
                if body is None:
                    return ""

                md_lines = []
                is_first = True
                for elem in body:
                    if elem.tag == f"{W_NS}p":
                        pPr = elem.find(f"{W_NS}pPr")
                        pStyle = pPr.find(f"{W_NS}pStyle") if pPr is not None else None
                        style_val = pStyle.attrib.get(f"{W_NS}val", "") if pStyle is not None else ""

                        text = "".join(node.text for node in elem.iter() if node.tag.endswith("}t") and node.text).strip()
                        if not text:
                            continue

                        text_lower = text.lower()
                        if is_first:
                            md_lines.append(f"# {text}")
                            is_first = False
                        elif "Heading1" in style_val:
                            md_lines.append(f"# {text}")
                        elif "Heading" in style_val or text_lower in KNOWN_SECTIONS:
                            md_lines.append(f"## {text}")
                        elif text.startswith("val ") or text.startswith("// ") or "client.send(" in text or "Client(" in text:
                            md_lines.append(f"```kotlin\n{text}\n```")
                        else:
                            md_lines.append(text)
                    elif elem.tag == f"{W_NS}tbl":
                        table_lines = []
                        rows = elem.findall(f"{W_NS}tr")
                        for r_idx, row in enumerate(rows):
                            cells = []
                            for cell in row.findall(f"{W_NS}tc"):
                                c_text = "".join(node.text for node in cell.iter() if node.tag.endswith("}t") and node.text).strip()
                                cells.append(c_text)
                            table_lines.append("| " + " | ".join(cells) + " |")
                            if r_idx == 0:
                                table_lines.append("| " + " | ".join(["---"] * len(cells)) + " |")
                        md_lines.append("\n".join(table_lines))

                return "\n\n".join(md_lines)
        except Exception:
            return ""

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

    def ingest_documents_from_paths(
        self,
        file_paths: list[str | Path],
        chunk_strategy: str = "fixed_size",
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> list[dict[str, Any]]:
        stored_documents: list[dict[str, Any]] = []

        for fp in file_paths:
            path = Path(fp)
            if not path.exists():
                continue
            suffix = path.suffix.lower()
            document_id = uuid4().hex
            created_at = self._timestamp()

            if suffix == ".docx":
                raw_text = self._extract_docx_markdown(path)
                raw_segments = [(None, raw_text)]
                source_type = "docx"
                page_count = None
            elif suffix == ".pdf":
                pages = self._extract_pdf_pages(path)
                raw_segments = pages
                source_type = "pdf"
                page_count = len(pages)
            else:
                raw_segments = self._extract_text_file(path)
                source_type = "text"
                page_count = None

            full_text = "\n\n".join(seg for _, seg in raw_segments)
            meta = self._infer_metadata(path.name, full_text)

            chunk_payloads: list[ChunkRecord] = []
            chunk_index = 0
            text_length = 0

            for page_number, segment_text in raw_segments:
                pieces = chunk_text(segment_text, chunk_size, overlap, strategy=chunk_strategy)
                text_length += len(segment_text)
                for piece in pieces:
                    chunk_id = uuid4().hex
                    embedding = self.embeddings.encode([piece])[0]
                    words = len(piece.split())
                    chars = len(piece)

                    chunk_rec = ChunkRecord(
                        id=chunk_id,
                        document_id=document_id,
                        document_filename=path.name,
                        chunk_index=chunk_index,
                        page_number=page_number,
                        text=piece,
                        embedding=embedding,
                        created_at=created_at,
                        chunk_strategy=chunk_strategy,
                        word_count=words,
                        char_count=chars,
                        source_file=meta["source_file"],
                        page_id=meta["page_id"],
                        sdk_version=meta["sdk_version"],
                        page_type=meta["page_type"],
                    )

                    # Strict Ingestion Rule: Validate source_file exists
                    if not chunk_rec.source_file:
                        raise ValueError(f"Strict Ingestion Failure: Chunk {chunk_id} has no source_file metadata!")

                    chunk_payloads.append(chunk_rec)
                    chunk_index += 1

            document = DocumentRecord(
                id=document_id,
                filename=path.name,
                source_type=source_type,
                stored_path=str(path),
                created_at=created_at,
                chunk_count=len(chunk_payloads),
                page_count=page_count,
                text_length=text_length,
                chunk_strategy=chunk_strategy,
                source_file=meta["source_file"],
                page_id=meta["page_id"],
                sdk_version=meta["sdk_version"],
                page_type=meta["page_type"],
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

    def ingest_uploads(
        self,
        uploads: Iterable[UploadFile],
        chunk_strategy: str = "fixed_size",
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> list[dict[str, Any]]:
        stored_documents: list[dict[str, Any]] = []

        for upload in uploads:
            content = upload.file.read()
            stored_path = self._write_upload(upload.filename, content)
            suffix = stored_path.suffix.lower()
            document_id = uuid4().hex
            created_at = self._timestamp()

            if suffix == ".docx":
                raw_text = self._extract_docx_markdown(stored_path)
                raw_segments = [(None, raw_text)]
                source_type = "docx"
                page_count = None
            elif suffix == ".pdf":
                pages = self._extract_pdf_pages(stored_path)
                raw_segments = pages
                source_type = "pdf"
                page_count = len(pages)
            else:
                raw_segments = self._extract_text_file(stored_path)
                source_type = "text"
                page_count = None

            full_text = "\n\n".join(seg for _, seg in raw_segments)
            meta = self._infer_metadata(upload.filename, full_text)

            chunk_payloads: list[ChunkRecord] = []
            chunk_index = 0
            text_length = 0

            for page_number, segment_text in raw_segments:
                pieces = chunk_text(segment_text, chunk_size, overlap, strategy=chunk_strategy)
                text_length += len(segment_text)
                for piece in pieces:
                    chunk_id = uuid4().hex
                    embedding = self.embeddings.encode([piece])[0]
                    words = len(piece.split())
                    chars = len(piece)

                    chunk_rec = ChunkRecord(
                        id=chunk_id,
                        document_id=document_id,
                        document_filename=upload.filename,
                        chunk_index=chunk_index,
                        page_number=page_number,
                        text=piece,
                        embedding=embedding,
                        created_at=created_at,
                        chunk_strategy=chunk_strategy,
                        word_count=words,
                        char_count=chars,
                        source_file=meta["source_file"],
                        page_id=meta["page_id"],
                        sdk_version=meta["sdk_version"],
                        page_type=meta["page_type"],
                    )

                    # Strict Ingestion Rule: Validate source_file exists
                    if not chunk_rec.source_file:
                        raise ValueError(f"Strict Ingestion Failure: Chunk {chunk_id} has no source_file metadata!")

                    chunk_payloads.append(chunk_rec)
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
                chunk_strategy=chunk_strategy,
                source_file=meta["source_file"],
                page_id=meta["page_id"],
                sdk_version=meta["sdk_version"],
                page_type=meta["page_type"],
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

    def clear_all_data(self) -> dict[str, Any]:
        from reset_data import reset_store_data
        reset_store_data()
        self.store = LocalStore()
        self.retriever = Retriever(self.store, self.embeddings)
        self.reset_hybrid_retriever()
        return {"cleared": True, "message": "All store and index data cleared successfully."}

    def delete_chunk(self, chunk_id: str) -> dict[str, Any]:

        chunk = self.store.get_chunk(chunk_id)
        if chunk is None:
            return {"deleted": False, "reason": "chunk_not_found"}

        self.retriever.delete_chunks([chunk_id])
        removed = self.store.delete_chunk(chunk_id)
        self.reset_hybrid_retriever()
        return {
            "deleted": removed is not None,
            "chunk_id": chunk_id,
            "document_id": chunk.document_id if removed is not None else None,
        }

    def get_hybrid_retriever(self) -> Any:
        if getattr(self, "_hybrid_retriever", None) is None:
            from week4.hybrid import HybridRetriever
            self._hybrid_retriever = HybridRetriever(self, rrf_k=60)
        return self._hybrid_retriever

    def get_multiquery_retriever(self) -> Any:
        if getattr(self, "_multiquery_retriever", None) is None:
            from week4.multi_query import MultiQueryBM25Retriever
            self._multiquery_retriever = MultiQueryBM25Retriever(self)
        return self._multiquery_retriever

    def reset_hybrid_retriever(self) -> None:
        self._hybrid_retriever = None
        self._multiquery_retriever = None

    def compare_retrieval(self, question: str, top_k: int = 3, debug: bool = False) -> dict[str, Any]:
        import json
        import time
        from pathlib import Path

        golden_set_file = Path("week4/golden_set.json")
        golden_item = None
        if golden_set_file.exists():
            try:
                gset = json.loads(golden_set_file.read_text(encoding="utf-8"))
                for item in gset:
                    if (
                        item["question"].strip().lower() == question.strip().lower()
                        or item["id"].strip().lower() == question.strip().lower()
                    ):
                        golden_item = item
                        break
            except Exception:
                pass

        # 1. Baseline: Dense Vector Search (Search full candidate pool to find exact global rank)
        t0 = time.perf_counter()
        dense_all = self.retriever.search(question, top_k=54)
        t1 = time.perf_counter()
        dense_latency_ms = (t1 - t0) * 1000.0
        dense_hits = dense_all[:top_k]

        # 2. Hybrid: BM25 + RRF (Search full candidate pool to find exact global rank)
        t2 = time.perf_counter()
        hybrid_all = self.get_hybrid_retriever().search(question, top_k=54, candidate_k=25)
        t3 = time.perf_counter()
        hybrid_latency_ms = (t3 - t2) * 1000.0
        hybrid_hits = hybrid_all[:top_k]

        # 3. Multi-Query (3x Top-4) + BM25 Re-rank
        t4 = time.perf_counter()
        mq_details = self.get_multiquery_retriever().search_with_details(question, top_k=top_k)
        t5 = time.perf_counter()
        mq_latency_ms = (t5 - t4) * 1000.0
        mq_hits = mq_details["top_chunks"]

        expected_chunk_id = golden_item["correct_chunk_id"] if golden_item else None

        dense_all_ids = [h["id"] for h in dense_all]
        hybrid_all_ids = [h["id"] for h in hybrid_all]
        mq_retrieved_ids = [h["id"] for h in mq_hits]

        dense_rank = (dense_all_ids.index(expected_chunk_id) + 1) if (expected_chunk_id and expected_chunk_id in dense_all_ids) else None
        hybrid_rank = (hybrid_all_ids.index(expected_chunk_id) + 1) if (expected_chunk_id and expected_chunk_id in hybrid_all_ids) else None
        mq_rank = (mq_retrieved_ids.index(expected_chunk_id) + 1) if (expected_chunk_id and expected_chunk_id in mq_retrieved_ids) else None

        dense_hit = (dense_rank is not None and dense_rank <= top_k) if expected_chunk_id else None
        hybrid_hit = (hybrid_rank is not None and hybrid_rank <= top_k) if expected_chunk_id else None
        mq_hit = (mq_rank is not None and mq_rank <= top_k) if expected_chunk_id else None

        dense_answer = self._build_local_answer(question, dense_hits)
        hybrid_answer = self._build_local_answer(question, hybrid_hits)
        mq_answer = self._build_local_answer(question, mq_hits)

        return {
            "question": question,
            "golden_item": golden_item,
            "expected_chunk_id": expected_chunk_id,
            "baseline": {
                "name": "Baseline (Dense Vector Only)",
                "mode": "dense",
                "hits": dense_hits,
                "hit_at_3": dense_hit,
                "target_rank": dense_rank,
                "latency_ms": round(dense_latency_ms, 2),
                "answer": dense_answer,
                "context_blocks": self._build_context_blocks(dense_hits),
            },
            "hybrid": {
                "name": "Week 4 Improved (BM25 + RRF)",
                "mode": "hybrid",
                "hits": hybrid_hits,
                "hit_at_3": hybrid_hit,
                "target_rank": hybrid_rank,
                "latency_ms": round(hybrid_latency_ms, 2),
                "answer": hybrid_answer,
                "context_blocks": self._build_context_blocks(hybrid_hits),
            },
            "multiquery": {
                "name": "Multi-Query (3x Top-4) + BM25",
                "mode": "multiquery",
                "hits": mq_hits,
                "hit_at_3": mq_hit,
                "target_rank": mq_rank,
                "latency_ms": round(mq_latency_ms, 2),
                "answer": mq_answer,
                "variations": mq_details.get("variations", []),
                "passes": mq_details.get("passes", []),
                "candidate_pool_size": len(mq_details.get("candidate_pool", [])),
                "context_blocks": self._build_context_blocks(mq_hits),
            },
        }

    def answer(
        self,
        question: str,
        top_k: int = 4,
        debug: bool = False,
        retrieval_mode: str = "hybrid",
    ) -> dict[str, Any]:
        return self._answer_one(question, top_k=top_k, debug=debug, retrieval_mode=retrieval_mode)

    def answer_batch(
        self,
        questions: list[str],
        top_k: int = 4,
        debug: bool = False,
        retrieval_mode: str = "hybrid",
    ) -> dict[str, Any]:
        results = [
            self._answer_one(question, top_k=top_k, debug=debug, retrieval_mode=retrieval_mode)
            for question in questions
            if question.strip()
        ]
        return {
            "count": len(results),
            "results": results,
        }

    def _answer_one(
        self,
        question: str,
        top_k: int = 4,
        debug: bool = False,
        retrieval_mode: str = "hybrid",
    ) -> dict[str, Any]:
        import time

        started_at = time.perf_counter()
        trace_id = uuid4().hex

        def finish(
            payload: dict[str, Any],
            retrieval: dict[str, Any] | None = None,
            raw_output: str | None = None,
            usage: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            payload["trace_id"] = trace_id
            hits = (retrieval or {}).get("hits", [])
            _write_trace_log(
                {
                    "trace_id": trace_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "question": question,
                    "prompt_version": "rag-answer-v1",
                    "retrieval": {
                        "mode": (retrieval or {}).get("mode"),
                        "tool_query": (retrieval or {}).get("tool_query"),
                        "tool_top_k": (retrieval or {}).get("tool_top_k"),
                        "chunks": [
                            {
                                "chunk_id": hit.get("id"),
                                "text": hit.get("text", ""),
                                "score": hit.get("score"),
                                "dense_score": hit.get("dense_score"),
                                "bm25_score": hit.get("bm25_score"),
                                "rrf_score": hit.get("rrf_score"),
                                "source_file": hit.get("source_file") or hit.get("document_filename"),
                                "sdk_version": hit.get("sdk_version"),
                                "page_number": hit.get("page_number"),
                            }
                            for hit in hits
                        ],
                    },
                    "model": {"name": self._active_model_name(), "temperature": 0.2, "usage": usage},
                    "raw_output": raw_output,
                    "answer": payload.get("answer"),
                    "used_llm": payload.get("used_llm", False),
                    "latency_ms": round((time.perf_counter() - started_at) * 1000.0, 2),
                }
            )
            return payload

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
            return finish(payload)

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
            return finish(payload)

        retrieval = self._retrieve_hits_for_question(question, top_k=top_k, debug=debug, retrieval_mode=retrieval_mode)
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
            return finish(payload, retrieval)

        effective_threshold = 0.005 if retrieval_mode in ("hybrid", "multiquery") else DEFAULT_SCORE_THRESHOLD
        best_score = hits[0].get("score") if hits[0].get("score") is not None else hits[0].get("rrf_score", 0.0)
        if best_score < effective_threshold:
            context_blocks = self._build_context_blocks(hits)
            payload = {
                "question": question,
                "answer": "I do not know. I could not find a relevant chunk in the indexed documents.",
                "sources": self._build_sources_from_blocks(context_blocks),
                "source_pages": self._extract_source_pages_from_blocks(context_blocks),
                "context": [],
                "chunks": hits,
                "used_llm": False,
                "structured_answer": None,
            }
            if debug:
                payload["debug"] = {
                    "reason": "score_below_threshold",
                    "threshold": effective_threshold,
                    "best_score": best_score,
                    "top_k": top_k,
                    "top_hits": self._debug_hits(hits),
                    "retrieval": retrieval,
                }
            return finish(payload, retrieval)

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
        raw_output = structured_debug.get("raw_json") if structured_answer is not None else answer_text
        usage = structured_debug.get("usage")
        if debug:
            if structured_answer is not None and structured_answer.knows_answer:
                reason = "answer_generated_with_llm"
            elif structured_answer is not None and not structured_answer.knows_answer:
                reason = "llm_did_not_find_answer_in_context"
            elif not used_llm:
                reason = "no_llm_key_local_fallback"
            else:
                reason = "llm_generation_failed"

            payload["debug"] = {
                "reason": reason,
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
        return finish(payload, retrieval, raw_output=raw_output, usage=usage)


    def _retrieve_hits_for_question(
        self,
        question: str,
        top_k: int,
        debug: bool = False,
        retrieval_mode: str = "hybrid",
    ) -> dict[str, Any]:
        provider_key = self.openrouter_api_key or self.openai_api_key
        if retrieval_mode == "hybrid":
            fallback_hits = self.get_hybrid_retriever().search(question, top_k=top_k, candidate_k=25)
        elif retrieval_mode == "multiquery":
            fallback_hits = self.get_multiquery_retriever().search(question, top_k=top_k)
        else:
            fallback_hits = self.retriever.search(question, top_k=top_k)

        result: dict[str, Any] = {
            "mode": f"fallback_{retrieval_mode}",
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

        if retrieval_mode == "hybrid":
            hits = self.get_hybrid_retriever().search(search_query, top_k=tool_top_k, candidate_k=25)
        else:
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
                "document_filename": hit.get("document_filename") or hit.get("source_file") or "Unknown",
                "page_number": hit.get("page_number"),
                "chunk_index": hit.get("chunk_index", 0),
                "score": round(hit.get("score") if hit.get("score") is not None else hit.get("rrf_score", 0.0), 4),
                "rrf_score": hit.get("rrf_score"),
                "bm25_score": hit.get("bm25_score"),
                "text_preview": snippet(hit.get("text", ""), 200),
                "chunk_id": hit.get("id", ""),
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
                    "document_filename": block["document_filename"],
                    "page_number": block["page_number"],
                    "chunk_index": block["chunk_index"],
                    "score": round(block.get("score", 0.0), 4),
                    "rrf_score": block.get("rrf_score"),
                    "preview": snippet(block.get("text", "")),
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
                    "document_id": hit.get("document_id", ""),
                    "document_filename": hit.get("document_filename") or hit.get("source_file") or "Unknown",
                    "page_number": hit.get("page_number"),
                    "chunk_index": hit.get("chunk_index", 0),
                    "text": hit.get("text", ""),
                    "score": hit.get("score") if hit.get("score") is not None else hit.get("rrf_score", 0.0),
                    "rrf_score": hit.get("rrf_score"),
                    "bm25_score": hit.get("bm25_score"),
                    "chunk_id": hit.get("id", ""),
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

    def _build_context_within_budget(
        self,
        question: str,
        context_blocks: list[dict[str, Any]],
        model_name: str,
        max_context_tokens: int = 4000,
    ) -> tuple[str, list[dict[str, Any]]]:
        included_blocks: list[dict[str, Any]] = []
        current_text = ""

        for block in context_blocks:
            test_blocks = included_blocks + [block]
            test_text = self._build_context(test_blocks)
            estimated_tokens = len(test_text) // 4
            if estimated_tokens > max_context_tokens and included_blocks:
                break
            included_blocks.append(block)
            current_text = test_text

        return current_text, included_blocks

    def _blocks_to_chunk_hits(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "id": block.get("chunk_id", ""),
                "document_id": block["document_id"],
                "document_filename": block["document_filename"],
                "page_number": block["page_number"],
                "chunk_index": block["chunk_index"],
                "text": block["text"],
                "score": block["score"],
            }
            for block in blocks
        ]

    def _context_budget_debug(
        self,
        question: str,
        model: str,
        all_blocks: list[dict[str, Any]],
        included_blocks: list[dict[str, Any]],
        context_text: str,
        max_context_tokens: int = 4000,
    ) -> dict[str, Any]:
        return {
            "model": model,
            "max_context_tokens": max_context_tokens,
            "total_blocks": len(all_blocks),
            "included_blocks": len(included_blocks),
            "estimated_context_tokens": len(context_text) // 4,
            "truncated": len(included_blocks) < len(all_blocks),
        }

    def _answer_prompt_prefix(self) -> str:
        return f"{answer_system_prompt()}\n\n{answer_examples()}\n\n"


    def _build_local_answer(self, question: str, hits: list[dict[str, Any]]) -> str:
        lines = [
            f"Question: {question}",
            "",
            "Grounded Answer (Extracted from retrieved context):",
        ]
        for hit in hits:
            filename = hit.get("document_filename") or hit.get("source_file") or "Document"
            page_part = "" if hit.get("page_number") is None else f", page {hit['page_number']}"
            score_val = hit.get("score") if hit.get("score") is not None else hit.get("rrf_score", 0.0)
            score_label = f"RRF: {hit['rrf_score']}" if hit.get("rrf_score") else f"score: {score_val:.3f}"
            lines.append(
                f"• {snippet(hit.get('text', ''), 280)} "
                f"[{filename}{page_part}, chunk {hit.get('chunk_index', 0)} ({score_label})]"
            )
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
        system_content = (
            f"{answer_system_prompt()}\n\n"
            "Here are examples of expected JSON responses:\n\n"
            f"{answer_examples()}"
        )

        user_content = (
            f"<context>\n{context_text}\n</context>\n\n"
            f"Question: {question}\n\n"
            "Based ONLY on the provided context, answer the question accurately. "
            "If the context contains the answer, set knows_answer to true, set confidence (0.0 to 1.0), list the reference block numbers used in used_sources, and include page numbers in page_numbers. "
            "Return valid JSON only matching the schema."
        )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
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

    def review_trace(self, trace_id: str | None = None) -> dict[str, Any]:
        """Review one stored trace with the configured LLM and append a notes entry."""
        from pathlib import Path
        traces = []
        if TRACE_FILE.exists():
            decoder = json.JSONDecoder()
            traces = []
            for line in TRACE_FILE.read_text(encoding="utf-8").splitlines():
                try: traces.append(json.loads(line))
                except json.JSONDecodeError: continue
        if trace_id is None or trace_id.strip().lower() in {"", "auto", "random"}:
            import random
            trace = random.choice(traces) if traces else None
            trace_id = trace.get("trace_id") if trace else None
        else:
            trace = next((item for item in traces if item.get("trace_id") == trace_id), None)
        if trace is None:
            raise ValueError(f"Trace not found: {trace_id}")
        prompt = ("Review this RAG trace. Decide whether its answer is correct, whether retrieved chunks are relevant, "
                  "and whether it matches the behavior of earlier traces. Return concise JSON with keys "
                  "same_as_previous, matching_trace_id, answer_quality, retrieval_quality, category, reason.\n\n" +
                  json.dumps(trace, ensure_ascii=False))
        response = self._call_llm([{"role": "system", "content": "You are a precise RAG trace evaluator. Return JSON only."}, {"role": "user", "content": prompt}])
        if response is None:
            raise RuntimeError("LLM review request failed")
        raw = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        try:
            review = json.loads(raw)
        except json.JSONDecodeError:
            review = {"category": "unparseable_review", "reason": raw}
        notes_path = Path("week5/notes.md")
        with notes_path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n\n### LLM Review — Trace `{trace_id}`\n\n")
            for key, value in review.items():
                handle.write(f"- **{key.replace('_', ' ').title()}**: {value}\n")
        return {"trace_id": trace_id, "review": review, "notes_path": str(notes_path)}
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

