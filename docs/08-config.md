# `rag/config.py`

This file holds project settings.

## Paths

- `DATA_DIR`  
  Main folder for stored files

- `UPLOAD_DIR`  
  Saved uploaded files

- `CHROMA_DIR`  
  Local Chroma database folder

- `DOCS_FILE`  
  JSON file for documents

- `CHUNKS_FILE`  
  JSON file for chunks

## RAG settings

- `DEFAULT_CHUNK_SIZE`  
  Number of words per chunk

- `DEFAULT_CHUNK_OVERLAP`  
  Words repeated between chunks

- `DEFAULT_TOP_K`  
  Number of chunks returned in search

- `DEFAULT_SCORE_THRESHOLD`  
  Minimum score before the app trusts a match

## Why this file matters

It keeps important constants in one place.

