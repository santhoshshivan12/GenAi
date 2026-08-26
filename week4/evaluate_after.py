from __future__ import annotations

import sys
from pathlib import Path

# Fix sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import statistics
import time
from rag.service import RAGService
from week4.hybrid import HybridRetriever

WEEK4_DIR = Path("week4")

def main():
    golden_set_path = WEEK4_DIR / "golden_set.json"
    if not golden_set_path.exists():
        raise FileNotFoundError(f"Missing {golden_set_path}. Run build_golden_set.py first!")

    golden_set = json.loads(golden_set_path.read_text(encoding="utf-8"))
    svc = RAGService()
    hybrid_retriever = HybridRetriever(svc, rrf_k=60)

    results = []
    latencies = []
    hits = 0

    print("======================================================================")
    print(" PHASE D: POST-IMPROVEMENT HYBRID SEARCH EVALUATION (BM25 + RRF k=60)")
    print("======================================================================")

    for q_item in golden_set:
        q_id = q_item["id"]
        question = q_item["question"]
        expected_chunk_id = q_item["correct_chunk_id"]

        start_time = time.perf_counter()
        top_chunks = hybrid_retriever.search(question, top_k=3, candidate_k=25)
        end_time = time.perf_counter()

        latency_ms = (end_time - start_time) * 1000.0
        latencies.append(latency_ms)

        retrieved_ids = [c["id"] for c in top_chunks]
        is_hit = expected_chunk_id in retrieved_ids

        if is_hit:
            hits += 1

        retrieved_details = []
        for rank, c in enumerate(top_chunks, start=1):
            retrieved_details.append({
                "rank": rank,
                "chunk_id": c["id"],
                "rrf_score": c.get("rrf_score", 0.0),
                "source_file": c.get("source_file"),
                "text_snippet": c["text"][:120]
            })

        result_record = {
            "question_id": q_id,
            "question": question,
            "expected_chunk_id": expected_chunk_id,
            "expected_source_file": q_item["source_file"],
            "retrieved": retrieved_details,
            "hit_at_3": is_hit,
            "latency_ms": round(latency_ms, 2)
        }
        results.append(result_record)

        hit_symbol = "[HIT]" if is_hit else "[MISS]"
        print(f" [{q_id}] {hit_symbol} ({latency_ms:.1f}ms) | Q: '{question}'")
        if not is_hit:
            print(f"       Expected: {expected_chunk_id} ({q_item['source_file']})")
            print(f"       Retrieved: {retrieved_ids}")

    hit_at_3_rate = (hits / len(golden_set)) * 100.0
    p50_latency = statistics.median(latencies)

    summary = {
        "total_questions": len(golden_set),
        "hits_at_3": hits,
        "hit_at_3_rate_pct": round(hit_at_3_rate, 2),
        "p50_latency_ms": round(p50_latency, 2),
        "question_results": results
    }

    after_out = WEEK4_DIR / "after_results.json"
    after_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n----------------------------------------------------------------------")
    print(f" After Hit@3 Score   : {hits} / {len(golden_set)} ({hit_at_3_rate:.2f}%)")
    print(f" After p50 Latency   : {p50_latency:.2f} ms")
    print(f" Saved raw results to: {after_out}")
    print("----------------------------------------------------------------------\n")

if __name__ == "__main__":
    main()
