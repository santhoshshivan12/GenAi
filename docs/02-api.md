# `rag/api.py`

This file defines the web app and the HTTP endpoints.

## Main endpoints

- `GET /`  
  Shows the dashboard in the browser.

- `POST /upload`  
  Uploads files and sends them into the ingestion pipeline.

- `POST /query`  
  Accepts a question and returns a grounded answer.

- `GET /documents`  
  Returns all stored documents as JSON.

- `GET /chunks`  
  Returns stored chunks as JSON.

- `GET /documents/{document_id}`  
  Shows one document and its chunks.

- `GET /health`  
  Simple health check.

## What the HTML page shows

- number of documents
- number of chunks
- upload form
- question form
- recent chunk previews
- stored document list

## In simple terms

This file is the front door of the app.

