from __future__ import annotations

import sys
from pathlib import Path

# Fix sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from rag.service import RAGService

WEEK4_DIR = Path("week4")

def main():
    baseline_path = WEEK4_DIR / "baseline_results.json"
    if not baseline_path.exists():
        raise FileNotFoundError(f"Missing {baseline_path}. Run evaluate_baseline.py first!")

    baseline_data = json.loads(baseline_path.read_text(encoding="utf-8"))
    svc = RAGService()

    misses = [q for q in baseline_data["question_results"] if not q["hit_at_3"]]

    print("======================================================================")
    print(f" PHASE B: FAILURE INSPECTION ({len(misses)} Misses Out Of {baseline_data['total_questions']} Questions)")
    print("======================================================================")

    inspection_records = []
    tally = {"R": 0, "G": 0, "Not-In-Corpus": 0}

    for miss in misses:
        q_id = miss["question_id"]
        question = miss["question"]
        expected_chunk_id = miss["expected_chunk_id"]

        # Search top-25 to check if expected chunk exists further down in retrieval ranking
        top25 = svc.retriever.search(question, top_k=25)
        top25_ids = [c["id"] for c in top25]

        expected_chunk_obj = svc.store.get_chunk(expected_chunk_id)
        
        if not expected_chunk_obj:
            classification = "Not-In-Corpus"
            evidence = f"Expected chunk {expected_chunk_id} does not exist in the store."
        elif expected_chunk_id in top25_ids:
            rank = top25_ids.index(expected_chunk_id) + 1
            classification = "R"
            evidence = f"Expected chunk {expected_chunk_id} ('{miss['expected_source_file']}') exists in store and ranked at #{rank} in top-25, but was excluded from Top-3."
        else:
            classification = "R"
            evidence = f"Expected chunk {expected_chunk_id} ('{miss['expected_source_file']}') was absent even from Top-25 search results due to dense vector similarity gap."

        tally[classification] += 1

        record = {
            "question_id": q_id,
            "question": question,
            "classification": classification,
            "expected_chunk_id": expected_chunk_id,
            "expected_source_file": miss["expected_source_file"],
            "retrieved_top3_chunk_ids": [c["chunk_id"] for c in miss["retrieved"]],
            "evidence": evidence
        }
        inspection_records.append(record)

        print(f"\n [{q_id}] Classification: [{classification}]")
        print(f"      Question: '{question}'")
        print(f"      Evidence: {evidence}")

    inspection_summary = {
        "total_misses": len(misses),
        "tally": tally,
        "inspections": inspection_records
    }

    out_file = WEEK4_DIR / "inspection_results.json"
    out_file.write_text(json.dumps(inspection_summary, indent=2), encoding="utf-8")

    print("\n----------------------------------------------------------------------")
    print(f" Failure Tally -> R (Retrieval): {tally['R']} | G (Generation): {tally['G']} | Not-In-Corpus: {tally['Not-In-Corpus']}")
    print(f" Saved inspection analysis to: {out_file}")
    print("----------------------------------------------------------------------\n")

if __name__ == "__main__":
    main()
