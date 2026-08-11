# Chunking Strategies

Chunking means splitting a long document into smaller pieces before indexing it.

## Why chunking exists

A retrieval system works better on smaller sections than on one giant block of text.

Chunking helps because:

- search is more precise
- embeddings represent a narrower idea
- citations can point to a smaller source section
- the app can retrieve only the relevant part of a document

## The main tradeoff

Chunk size is a balance.

- too small: chunks lose context
- too large: chunks become hard to match accurately

## Common chunking styles

### 1. Fixed-size chunking

Split the text into chunks with a set size, for example 300 to 800 words.

This is simple and common in RAG systems.

### 2. Overlapping chunking

Each chunk shares some text with the next chunk.

This helps when useful information spans a boundary.

Example:

- chunk 1 ends with the start of a definition
- chunk 2 begins with the same definition and continues it

### 3. Semantic chunking

Split based on meaning, headings, or paragraph structure instead of a fixed size.

This can preserve better context, but it is more complex.

## What overlap does

Overlap reduces the chance that important context is cut in half.

If chunk A ends with a key sentence and chunk B begins with it, the retriever is more likely to keep the context intact.

## Good starting values

For a small RAG demo:

- chunk size: 300 to 800 words
- overlap: 50 to 150 words

For your current app, chunking is word-based and uses overlap so neighboring chunks stay connected.

## When to use smaller chunks

Use smaller chunks when:

- documents are highly structured
- answers are short and factual
- you need high precision

## When to use larger chunks

Use larger chunks when:

- context is important
- the document contains explanations or procedures
- you want fewer chunks per document

## Practical rule

If retrieval is returning relevant but incomplete answers, increase overlap.

If retrieval is returning too much unrelated text, reduce chunk size.

