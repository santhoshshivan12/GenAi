# `rag/retriever.py`

This file handles search.

## What it does

- stores chunk embeddings in Chroma when available
- falls back to local similarity search if needed
- finds the top matching chunks for a question

## Search flow

1. Convert the question into an embedding.
2. Compare it with stored chunk embeddings.
3. Rank the chunks by similarity.
4. Return the best matches.

## Why it matters

This is the "retrieval" part of RAG.

It decides which chunks the answer should be based on.

## Chroma fallback

If Chroma is not available, the app still works.

In that case it compares the query embedding against all stored chunks in memory.

