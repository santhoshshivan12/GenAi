from __future__ import annotations

import re
from typing import Any
from rag.service import RAGService
from week4.hybrid import SimpleBM25


def generate_query_variations(question: str) -> list[str]:
    """
    Generate 3 distinct structural variations of a user question while preserving the exact context:
    1. Variation 1: Original Question (Direct user intent)
    2. Variation 2: Technical & Code Symbol Keywords (API symbols, method names, config properties)
    3. Variation 3: Functional / Behavioral Action (How-to configure, handle, or listen)
    """
    clean_q = question.strip()
    words = re.findall(r"\w+", clean_q)
    
    # 1. Original
    v1 = clean_q
    
    # 2. Technical / API keywords (filter stopwords and add documentation terms)
    stopwords = {"what", "which", "how", "do", "you", "is", "used", "to", "a", "an", "the", "in", "from", "for", "with", "when", "occurs", "checks", "trigger"}
    meaningful_words = [w for w in words if w.lower() not in stopwords]
    v2 = f"{' '.join(meaningful_words)} API method class configuration"
    
    # 3. Functional / Behavioral phrasing
    core_topic = " ".join(words[2:]) if len(words) > 2 else clean_q
    v3 = f"guide and code example for {core_topic}"
    
    return [v1, v2, v3]


class MultiQueryBM25Retriever:
    """
    Multi-Query Expansion (3 Variations) -> 3x Top-4 Retrieval -> BM25 Keyword Re-Ranking.
    """

    def __init__(self, service: RAGService):
        self.svc = service

    def search_with_details(self, question: str, top_k: int = 3) -> dict[str, Any]:
        if not question.strip():
            return {
                "variations": [],
                "passes": [],
                "candidate_pool": [],
                "top_chunks": []
            }

        # Step 1: Generate 3 question variations
        variations = generate_query_variations(question)

        # Step 2: Retrieve Top-4 chunks for each variation
        passes = []
        candidate_pool_map: dict[str, dict[str, Any]] = {}

        for pass_num, q_var in enumerate(variations, start=1):
            hits = self.svc.retriever.search(q_var, top_k=4)
            pass_hits = []
            for rank, hit in enumerate(hits, start=1):
                c_id = hit["id"]
                hit_dict = dict(hit)
                hit_dict["pass_rank"] = rank
                hit_dict["pass_query"] = q_var
                pass_hits.append(hit_dict)
                if c_id not in candidate_pool_map:
                    candidate_pool_map[c_id] = hit_dict

            passes.append({
                "pass_number": pass_num,
                "variation_query": q_var,
                "retrieved_count": len(hits),
                "hits": pass_hits
            })

        candidate_chunks = list(candidate_pool_map.values())
        if not candidate_chunks:
            return {
                "variations": variations,
                "passes": passes,
                "candidate_pool": [],
                "top_chunks": []
            }

        # Step 3: Apply BM25 keyword scoring on the candidate pool
        bm25 = SimpleBM25([c["text"] for c in candidate_chunks])
        bm25_scores = bm25.get_scores(question)

        for idx, score in enumerate(bm25_scores):
            candidate_chunks[idx]["bm25_rerank_score"] = round(score, 4)
            candidate_chunks[idx]["score"] = round(score, 4)

        # Step 4: Re-rank candidates by BM25 score descending
        candidate_chunks.sort(key=lambda x: x["bm25_rerank_score"], reverse=True)

        return {
            "variations": variations,
            "passes": passes,
            "candidate_pool": candidate_chunks,
            "top_chunks": candidate_chunks[:top_k]
        }

    def search(self, question: str, top_k: int = 3) -> list[dict[str, Any]]:
        details = self.search_with_details(question, top_k=top_k)
        return details["top_chunks"]
