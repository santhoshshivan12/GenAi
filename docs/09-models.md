# `rag/models.py`

This file defines the data structures used by the app.

## `DocumentRecord`

Represents one uploaded file.

It stores:

- file id
- filename
- source type
- storage path
- creation time
- number of chunks
- page count
- text length

## `ChunkRecord`

Represents one chunk of text from a document.

It stores:

- chunk id
- document id
- original filename
- chunk index
- page number
- chunk text
- embedding
- creation time

## Why models are useful

They make the data structure clear and keep the code consistent.

