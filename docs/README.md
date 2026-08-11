# RAG Project Guide

Start here if you want to understand the project from top to bottom.

## Reading order

1. [00-overview.md](./00-overview.md)
2. [01-main.md](./01-main.md)
3. [02-api.md](./02-api.md)
4. [03-service.md](./03-service.md)
5. [04-retriever.md](./04-retriever.md)
6. [05-store.md](./05-store.md)
7. [06-embeddings.md](./06-embeddings.md)
8. [07-utils.md](./07-utils.md)
9. [08-config.md](./08-config.md)
10. [09-models.md](./09-models.md)
11. [11-embedding-models-mteb-bge-e5.md](./11-embedding-models-mteb-bge-e5.md)
12. [12-chunking-strategies.md](./12-chunking-strategies.md)
13. [13-bi-encoder-vs-cross-encoder.md](./13-bi-encoder-vs-cross-encoder.md)
14. [14-vector-databases-hnsw-qdrant-chroma-pgvector.md](./14-vector-databases-hnsw-qdrant-chroma-pgvector.md)

## What the project does

This project is a small Retrieval-Augmented Generation app built with FastAPI.

It lets you:

- upload PDF or text files
- split them into chunks
- create embeddings for each chunk
- store the chunks locally
- search for the most relevant chunks
- return an answer with source references
- inspect the raw documents and chunks in the browser
