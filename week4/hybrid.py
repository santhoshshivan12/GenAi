from __future__ import annotations

import math
import re
from typing import Any
from rag.service import RAGService

def tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase alphanumeric tokens and code symbols."""
    return [t.lower() for t in re.findall(r"\w+", text)]

class SimpleBM25:
    """Pure Python BM25Okapi implementation for lightweight, zero-dependency hybrid search."""

    def __init__(self, corpus_texts: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus_texts)
        self.doc_tokens = [tokenize(t) for t in corpus_texts]
        self.doc_lens = [len(t) for t in self.doc_tokens]
        self.avgdl = sum(self.doc_lens) / self.corpus_size if self.corpus_size > 0 else 1.0

        # Calculate Document Frequency (DF)
        self.df: dict[str, int] = {}
        for tokens in self.doc_tokens:
            for token in set(tokens):
                self.df[token] = self.df.get(token, 0) + 1

        # Calculate Inverse Document Frequency (IDF)
        self.idf: dict[str, float] = {}
        for token, freq in self.df.items():
            self.idf[token] = math.log((self.corpus_size - freq + 0.5) / (freq + 0.5) + 1.0)

    def get_scores(self, query: str) -> list[float]:
        query_tokens = tokenize(query)
        scores = [0.0] * self.corpus_size

        for idx, tokens in enumerate(self.doc_tokens):
            if not tokens:
                continue
            doc_len = self.doc_lens[idx]
            token_counts: dict[str, int] = {}
            for t in tokens:
                token_counts[t] = token_counts.get(t, 0) + 1

            doc_score = 0.0
            for q_token in query_tokens:
                if q_token not in token_counts:
                    continue
                tf = token_counts[q_token]
                idf = self.idf.get(q_token, 0.0)
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avgdl))
                doc_score += idf * (numerator / denominator)

            scores[idx] = doc_score
        return scores


class HybridRetriever:
    """Hybrid Retriever combining Dense Vector Search + BM25 Lexical Search via RRF (k=60)."""

    def __init__(self, service: RAGService, rrf_k: int = 60):
        self.svc = service
        self.rrf_k = rrf_k
        self.chunks = self.svc.store.list_chunks()
        self.bm25 = SimpleBM25([c.text for c in self.chunks])

    def search(self, question: str, top_k: int = 3, candidate_k: int = 25) -> list[dict[str, Any]]:
        if not question.strip() or not self.chunks:
            return []

        # 1. Dense Vector Search (Top-25)
        dense_hits = self.svc.retriever.search(question, top_k=candidate_k)

        # 2. BM25 Lexical Search (Top-25)
        bm25_scores = self.bm25.get_scores(question)
        bm25_indexed = list(zip(range(len(self.chunks)), bm25_scores))
        bm25_indexed.sort(key=lambda x: x[1], reverse=True)
        top_bm25_indexed = bm25_indexed[:candidate_k]

        bm25_hits = []
        for idx, score in top_bm25_indexed:
            chunk = self.chunks[idx]
            bm25_hits.append({
                "id": chunk.id,
                "text": chunk.text,
                "score": score,
                "bm25_score": round(score, 4),
                "document_id": chunk.document_id,
                "document_filename": chunk.document_filename,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "chunk_strategy": getattr(chunk, "chunk_strategy", "fixed_size"),
                "word_count": getattr(chunk, "word_count", 0),
                "char_count": getattr(chunk, "char_count", 0),
                "source_file": getattr(chunk, "source_file", chunk.document_filename),
                "page_id": getattr(chunk, "page_id", ""),
                "sdk_version": getattr(chunk, "sdk_version", None),
                "page_type": getattr(chunk, "page_type", ""),
            })

        # 3. Reciprocal Rank Fusion (RRF k=60)
        rrf_scores: dict[str, float] = {}
        chunk_map: dict[str, dict[str, Any]] = {}

        # Dense RRF scoring
        for rank, hit in enumerate(dense_hits, start=1):
            c_id = hit["id"]
            hit_copy = dict(hit)
            hit_copy["dense_rank"] = rank
            hit_copy["dense_score"] = hit.get("score")
            chunk_map[c_id] = hit_copy
            rrf_scores[c_id] = rrf_scores.get(c_id, 0.0) + (1.0 / (self.rrf_k + rank))

        # BM25 RRF scoring
        for rank, hit in enumerate(bm25_hits, start=1):
            c_id = hit["id"]
            if c_id not in chunk_map:
                chunk_map[c_id] = dict(hit)
            chunk_map[c_id]["bm25_rank"] = rank
            chunk_map[c_id]["bm25_score"] = hit.get("score")
            rrf_scores[c_id] = rrf_scores.get(c_id, 0.0) + (1.0 / (self.rrf_k + rank))

        # Sort combined results by RRF score descending
        fused_sorted = sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)

        final_hits = []
        for c_id, score in fused_sorted[:top_k]:
            item = dict(chunk_map[c_id])
            item["rrf_score"] = round(score, 6)
            item["score"] = round(score, 6)
            final_hits.append(item)

        return final_hits
