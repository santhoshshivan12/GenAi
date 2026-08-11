# Vector Databases: HNSW, Qdrant, Chroma, pgvector

Vector databases store embeddings and make similarity search fast.

## What they do

They let you:

- store embeddings
- search by meaning
- filter by metadata
- retrieve top-K similar chunks quickly

## 1. HNSW

HNSW stands for **Hierarchical Navigable Small World**.

It is a vector search index algorithm, not a full database.

### Why it matters

HNSW makes nearest-neighbor search fast.

Many vector databases use it as part of their indexing system.

### In simple terms

HNSW is the engine that helps the database find close vectors quickly.

## 2. Qdrant

Qdrant is a dedicated vector database.

### Strengths

- strong vector search
- metadata filtering
- production-ready
- easy to use for RAG

### Best for

- apps that need a proper vector service
- search with filters
- scaling beyond local storage

## 3. Chroma

Chroma is a lightweight vector database for local or small-scale RAG apps.

### Strengths

- simple to set up
- easy for demos and prototypes
- works well for local development

### Best for

- proof of concept
- local RAG apps
- fast iteration

### In your app

Your project uses Chroma when available, because it is simple and works well for local ingestion and search.

## 4. pgvector

pgvector is a PostgreSQL extension for vector similarity search.

### Strengths

- uses existing Postgres infrastructure
- supports relational data and vectors together
- good if your app already uses Postgres

### Best for

- teams already using PostgreSQL
- apps that want one database for metadata and vectors
- production systems that prefer Postgres operations

## How to choose

### Choose HNSW-based search when:

- you want fast nearest-neighbor search
- you are okay with an indexing layer inside a vector DB

### Choose Qdrant when:

- you need a dedicated vector database
- you need filtering and production stability

### Choose Chroma when:

- you want something simple and local
- you are building a demo or prototype

### Choose pgvector when:

- you already use PostgreSQL
- you want vectors in the same database as your app data

## Practical view for your project

For learning and demos:

- Chroma is enough

For production search:

- Qdrant or pgvector are usually stronger choices

## Short version

- **HNSW** = fast vector search index
- **Qdrant** = dedicated vector database
- **Chroma** = simple local vector database
- **pgvector** = vector search inside PostgreSQL

