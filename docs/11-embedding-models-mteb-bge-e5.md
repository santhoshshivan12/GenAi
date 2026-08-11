# Embedding Models: MTEB, BGE, E5

This topic is often grouped together, but the terms mean different things.

## 1. MTEB

MTEB stands for **Massive Text Embedding Benchmark**.

It is **not** an embedding model.

It is a benchmark used to compare embedding models across tasks such as:

- semantic search
- clustering
- retrieval
- classification
- reranking

### Why MTEB matters

When people say a model is "good on MTEB", they mean it performs well on that benchmark.

That makes it useful for choosing between embedding models.

### In simple terms

MTEB is the test. It helps you measure which embedding model is better.

## 2. BGE

BGE stands for **BAAI General Embedding**.

It is a family of embedding models designed for retrieval and semantic search.

### Why people use BGE

- strong retrieval quality
- good performance on benchmark-style tasks
- available in different sizes
- often used for RAG pipelines

### Typical use case

Use BGE when you want embeddings for:

- document search
- question answering over documents
- vector database retrieval

### In simple terms

BGE is the actual model that turns text into vectors.

## 3. E5

E5 is a family of embedding models designed for text retrieval.

The name usually refers to models trained with query-document matching in mind.

### Why E5 is popular

- very strong for search tasks
- works well in retrieval-augmented generation
- query and passage style works naturally for RAG

### Common pattern

E5-style models often work best when you format input like:

- `query: what is RAG?`
- `passage: RAG means retrieval augmented generation`

That helps the model understand whether text is a question or a document chunk.

### In simple terms

E5 is another real embedding model family, often very good for search and retrieval.

## 4. How They Relate

Think of them like this:

- **MTEB** = benchmark
- **BGE** = embedding model family
- **E5** = embedding model family

So you do **not** choose MTEB as a model.

You use MTEB to compare models like BGE and E5.

## 5. What This Means for Your RAG App

For your FastAPI RAG app, the embedding model is what creates the vectors for each chunk.

That means:

- better embeddings usually improve retrieval
- better retrieval usually improves answer quality
- the chunk you retrieve is what the answer should be grounded in

## 6. Practical Recommendation

If you are building a local RAG demo:

- start with a small sentence-transformers model
- then compare it with BGE or E5
- use MTEB results as a reference if you want a stronger model choice

## 7. Short Version

- **MTEB** tells you how good an embedding model is
- **BGE** is an embedding model family for retrieval
- **E5** is another embedding model family for retrieval

