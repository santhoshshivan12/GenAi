# Overview

This project is a local RAG demo.

RAG means:

- **Retrieval**: find the most relevant text from your documents
- **Augmented**: add that text to the question
- **Generation**: produce an answer from the retrieved text

## Flow

1. You upload a PDF or `.txt` file.
2. The app saves the file in `data/uploads`.
3. The text is extracted from the file.
4. The text is split into smaller chunks.
5. Each chunk is converted into an embedding.
6. The chunk and its embedding are stored.
7. When you ask a question, the app searches for the closest chunks.
8. The answer is built from those chunks and shown with citations.

## Why chunking matters

Large documents are too big to search as one block.

Chunking helps because:

- smaller pieces are easier to match with a question
- the app can return the exact section that matters
- citations become more precise

## Why embeddings matter

Embeddings turn text into numbers.

That allows the app to compare meaning instead of only matching keywords.

## What you can inspect

You can see:

- uploaded documents
- chunk previews
- chunk counts
- the JSON output from the API

