from __future__ import annotations

import os
import shutil
from pathlib import Path


def reset_store_data():
    data_dir = Path("data")
    docs_file = data_dir / "documents.json"
    chunks_file = data_dir / "chunks.json"
    chroma_dir = data_dir / "chroma"
    uploads_dir = data_dir / "uploads"

    data_dir.mkdir(parents=True, exist_ok=True)
    docs_file.write_text("[]", encoding="utf-8")
    chunks_file.write_text("[]", encoding="utf-8")

    if chroma_dir.exists():
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(chroma_dir))
            try:
                client.delete_collection("rag_collection")
            except Exception:
                pass
            client.get_or_create_collection("rag_collection", metadata={"hnsw:space": "cosine"})
        except Exception as e:
            print(f"Chroma clear note: {e}")

    if uploads_dir.exists():
        try:
            shutil.rmtree(uploads_dir)
            uploads_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"Warning clearing uploads dir: {e}")

    print("SUCCESS: Data store reset cleanly! (documents.json, chunks.json, chroma index cleared)")



if __name__ == "__main__":
    reset_store_data()
