# `rag/service.py`

This is the main business logic layer.

## What it does

- receives uploaded files
- saves files to disk
- reads PDF pages or text files
- cleans the text
- splits the text into chunks
- creates embeddings
- stores document metadata
- stores chunk metadata
- runs question answering

## Key methods

### `ingest_uploads`

This method takes uploaded files and processes them end to end.

It:

- saves the uploaded file
- extracts text
- chunks the text
- creates embeddings
- stores the document and chunks

### `answer`

This method:

- searches for relevant chunks
- checks if the match is strong enough
- returns an answer with sources
- returns "I do not know" when nothing relevant is found

## Why this file matters

This is where the RAG pipeline really happens.

