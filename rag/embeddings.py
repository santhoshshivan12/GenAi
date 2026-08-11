from __future__ import annotations

from functools import lru_cache
from hashlib import blake2b
from math import log
from typing import Iterable


class EmbeddingBackend:
    def __init__(self) -> None:
        self._model = None
        self._dimension = 384

        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            self._dimension = 384
        except Exception:
            self._model = None
            self._dimension = 256

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode(self, texts: Iterable[str]) -> list[list[float]]:
        values = list(texts)
        if self._model is not None:
            embeddings = self._model.encode(values, normalize_embeddings=True)
            return [list(map(float, vector)) for vector in embeddings]
        return [self._hash_embed(text) for text in values]

    @lru_cache(maxsize=2048)
    def _hash_embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        words = [word.lower() for word in text.split()]
        if not words:
            return vector

        for word in words:
            digest = blake2b(word.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest, "big") % self._dimension
            vector[index] += 1.0

        norm = sum(value * value for value in vector) ** 0.5
        if norm:
            vector = [value / norm for value in vector]
        return vector

