# `rag/embeddings.py`

This file turns text into vectors.

## What an embedding is

An embedding is a list of numbers that represents the meaning of text.

Texts with similar meaning end up close together in vector space.

## How this file works

It tries to load `sentence-transformers` first.

If that works, it uses the `all-MiniLM-L6-v2` model.

If the model cannot load, it falls back to a lightweight hash-based embedding so the app still works.

## Why embeddings matter

Keyword search only matches exact words.

Embeddings allow semantic search, so the app can find related text even if the wording is different.

