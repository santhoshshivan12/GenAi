from __future__ import annotations

from typing import Any

from rag.config import CHROMA_COLLECTION, CHROMA_DIR
from rag.embeddings import EmbeddingBackend
from rag.store import LocalStore
from rag.utils import cosine_similarity


class Retriever:
    def __init__(self, store: LocalStore, embeddings: EmbeddingBackend) -> None:
        self.store = store
        self.embeddings = embeddings
        self._chroma = None
        self._collection = None

        try:
            import chromadb

            client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            self._collection = client.get_or_create_collection(
                name=CHROMA_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
            self._chroma = client
        except Exception:
            self._chroma = None
            self._collection = None

        if self._collection is not None:
            try:
                existing_count = self._collection.count()
                if existing_count == 0:
                    self._sync_from_store()
            except Exception:
                pass

    def _sync_from_store(self) -> None:
        chunks = self.store.list_chunks()
        if chunks:
            self.add_chunks([chunk.to_dict() for chunk in chunks])

    def add_chunks(self, chunks: list[dict[str, Any]]) -> None:
        if not chunks:
            return

        if self._collection is not None:
            self._collection.add(
                ids=[item["id"] for item in chunks],
                documents=[item["text"] for item in chunks],
                metadatas=[
                    {
                        "document_id": item["document_id"],
                        "document_filename": item["document_filename"],
                        "chunk_index": item["chunk_index"],
                        "page_number": item["page_number"] if item["page_number"] is not None else -1,
                        "created_at": item["created_at"],
                    }
                    for item in chunks
                ],
                embeddings=[item["embedding"] for item in chunks],
            )

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        if self._collection is not None:
            self._collection.delete(ids=chunk_ids)

    def delete_document(self, document_id: str) -> None:
        chunks = self.store.get_chunks_for_document(document_id)
        self.delete_chunks([chunk.id for chunk in chunks])

    def search(self, question: str, top_k: int) -> list[dict[str, Any]]:
        if not question.strip():
            return []

        if self._collection is not None:
            query_embedding = self.embeddings.encode([question])[0]
            result = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )
            hits: list[dict[str, Any]] = []
            documents = result.get("documents", [[]])[0]
            metadatas = result.get("metadatas", [[]])[0]
            distances = result.get("distances", [[]])[0]
            ids = result.get("ids", [[]])[0]
            for chunk_id, text, metadata, distance in zip(ids, documents, metadatas, distances):
                score = max(0.0, 1.0 - float(distance))
                hits.append(
                    {
                        "id": chunk_id,
                        "text": text,
                        "score": score,
                        "document_id": metadata.get("document_id"),
                        "document_filename": metadata.get("document_filename"),
                        "chunk_index": metadata.get("chunk_index"),
                        "page_number": metadata.get("page_number") if metadata.get("page_number") != -1 else None,
                    }
                )
            return hits

        query_embedding = self.embeddings.encode([question])[0]
        candidates = []
        for chunk in self.store.list_chunks():
            score = cosine_similarity(query_embedding, chunk.embedding)
            candidates.append(
                {
                    "id": chunk.id,
                    "text": chunk.text,
                    "score": score,
                    "document_id": chunk.document_id,
                    "document_filename": chunk.document_filename,
                    "chunk_index": chunk.chunk_index,
                    "page_number": chunk.page_number,
                }
            )
        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates[:top_k]
