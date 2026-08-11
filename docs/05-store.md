# `rag/store.py`

This file handles local persistence.

## What it stores

- documents
- chunks

## Storage format

It saves data as JSON files:

- `data/documents.json`
- `data/chunks.json`

## Why this matters

This makes the app easy to inspect.

You can open the JSON files and see:

- file names
- chunk text
- embeddings
- page numbers
- timestamps

## Main idea

This file is a small local database built with JSON.

