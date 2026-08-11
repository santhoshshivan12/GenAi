# `rag/utils.py`

This file contains helper functions.

## Functions

### `ensure_dirs`

Creates folders if they do not exist.

### `clean_text`

Normalizes text by removing extra whitespace and null characters.

### `chunk_text`

Splits long text into smaller chunks using word-based windows.

### `snippet`

Creates a short preview string for display in the UI.

### `slugify_filename`

Turns a filename into a safe lowercase name for storage.

### `cosine_similarity`

Measures how close two vectors are.

## Why this file exists

It keeps small reusable logic out of the main pipeline.

