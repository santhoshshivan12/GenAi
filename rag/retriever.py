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
            try:
                self._collection = client.get_collection(name=CHROMA_COLLECTION)
            except Exception:
                self._collection = client.create_collection(
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

    def _get_max_batch_size(self) -> int:
        if self._chroma is not None and hasattr(self._chroma, "get_max_batch_size"):
            try:
                return self._chroma.get_max_batch_size()
            except Exception:
                pass
        return 1000

    def add_chunks(self, chunks: list[dict[str, Any]]) -> None:
        if not chunks:
            return

        if self._collection is not None:
            batch_size = self._get_max_batch_size()
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i : i + batch_size]
                ids_list = [item["id"] for item in batch]
                docs_list = [item["text"] for item in batch]
                meta_list = [
                    {
                        "document_id": item["document_id"],
                        "document_filename": item["document_filename"],
                        "chunk_index": item["chunk_index"],
                        "page_number": item["page_number"] if item["page_number"] is not None else -1,
                        "created_at": item["created_at"],
                        "chunk_strategy": item.get("chunk_strategy", "fixed_size"),
                        "word_count": item.get("word_count", 0),
                        "char_count": item.get("char_count", 0),
                        "source_file": item.get("source_file") or "",
                        "page_id": item.get("page_id") or "",
                        "sdk_version": item.get("sdk_version") or "",
                        "page_type": item.get("page_type") or "",
                    }
                    for item in batch
                ]
                emb_list = [item["embedding"] for item in batch]

                try:
                    self._collection.add(
                        ids=ids_list,
                        documents=docs_list,
                        metadatas=meta_list,
                        embeddings=emb_list,
                    )
                except Exception as e:
                    if "dimension" in str(e).lower() or "expecting" in str(e).lower():
                        try:
                            self._chroma.delete_collection(CHROMA_COLLECTION)
                        except Exception:
                            pass
                        self._collection = self._chroma.create_collection(
                            name=CHROMA_COLLECTION,
                            metadata={"hnsw:space": "cosine"},
                        )
                        self._collection.add(
                            ids=ids_list,
                            documents=docs_list,
                            metadatas=meta_list,
                            embeddings=emb_list,
                        )
                    else:
                        raise e


    def delete_chunks(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        if self._collection is not None:
            batch_size = self._get_max_batch_size()
            for i in range(0, len(chunk_ids), batch_size):
                batch = chunk_ids[i : i + batch_size]
                self._collection.delete(ids=batch)

    def delete_document(self, document_id: str) -> None:
        chunks = self.store.get_chunks_for_document(document_id)
        self.delete_chunks([chunk.id for chunk in chunks])

    def search(
        self,
        question: str,
        top_k: int,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not question.strip():
            return []

        if self._collection is not None:
            query_embedding = self.embeddings.encode([question])[0]
            query_kwargs: dict[str, Any] = {
                "query_embeddings": [query_embedding],
                "n_results": top_k,
                "include": ["documents", "metadatas", "distances"],
            }
            if metadata_filter:
                query_kwargs["where"] = metadata_filter

            result = self._collection.query(**query_kwargs)
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
                        "chunk_strategy": metadata.get("chunk_strategy", "fixed_size"),
                        "word_count": metadata.get("word_count"),
                        "char_count": metadata.get("char_count"),
                        "source_file": metadata.get("source_file"),
                        "page_id": metadata.get("page_id"),
                        "sdk_version": metadata.get("sdk_version"),
                        "page_type": metadata.get("page_type"),
                    }
                )
            return hits

        query_embedding = self.embeddings.encode([question])[0]
        candidates = []
        chunks = self.store.list_chunks()
        if metadata_filter:
            filtered_chunks = []
            for chunk in chunks:
                match = True
                for k, v in metadata_filter.items():
                    if getattr(chunk, k, None) != v:
                        match = False
                        break
                if match:
                    filtered_chunks.append(chunk)
            chunks = filtered_chunks

        for chunk in chunks:
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
                    "chunk_strategy": getattr(chunk, "chunk_strategy", "fixed_size"),
                    "word_count": getattr(chunk, "word_count", None),
                    "char_count": getattr(chunk, "char_count", None),
                    "source_file": getattr(chunk, "source_file", None),
                    "page_id": getattr(chunk, "page_id", None),
                    "sdk_version": getattr(chunk, "sdk_version", None),
                    "page_type": getattr(chunk, "page_type", None),
                }
            )
        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates[:top_k]

