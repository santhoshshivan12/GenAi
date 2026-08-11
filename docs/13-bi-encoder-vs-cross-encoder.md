# Bi-Encoder vs Cross-Encoder

These are two different ways to compare a question with a document chunk.

## Bi-encoder

A bi-encoder encodes the query and the document separately.

### How it works

1. Convert the question into a vector.
2. Convert each chunk into a vector.
3. Compare the vectors with cosine similarity or another distance metric.

### Why it is used in RAG

It is fast and scales well.

You can precompute document embeddings once and reuse them.

### Strengths

- fast retrieval
- good for large document sets
- works well with vector databases

### Weaknesses

- less precise than a cross-encoder
- can miss subtle relationships

## Cross-encoder

A cross-encoder reads the question and chunk together.

### How it works

It takes both texts as one pair and predicts how relevant the chunk is to the query.

### Why it is accurate

Because it sees the full pair at once, it can reason about the exact relationship between the query and the chunk.

### Strengths

- more accurate ranking
- better for reranking top matches

### Weaknesses

- slower
- expensive to run over many chunks

## Typical RAG workflow

A common design is:

1. Use a bi-encoder to find the top candidate chunks quickly.
2. Use a cross-encoder to rerank those top candidates.
3. Send the best chunks to the generation step.

## Simple comparison

- **Bi-encoder** = fast search
- **Cross-encoder** = accurate reranking

## What this means for your app

Your FastAPI RAG app is currently using the bi-encoder pattern:

- question embedding
- chunk embeddings
- similarity search

That is the normal starting point for retrieval.

If you later want better precision, you can add a cross-encoder reranker on top of the top-K results.

