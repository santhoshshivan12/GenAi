from __future__ import annotations

import json
from html import escape
from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from rag.service import RAGService
from rag.utils import snippet

app = FastAPI(title="RAG Demo", version="1.0.0")
service = RAGService()


def format_source_item(item: dict[str, Any]) -> str:
    filename = item.get("filename") or item.get("document_filename") or "Unknown"
    page_num = item.get("page_number")
    page = "" if page_num is None else f" page {page_num}"
    chunk_index = item.get("chunk_index", 0)
    score = item.get("score", 0.0)
    return (
        f"<li><strong>{escape(str(filename))}</strong>"
        f"{page} chunk {chunk_index} - score {score}</li>"
    )



def format_context_item(block: dict[str, Any]) -> str:
    page = "" if block["page_number"] is None else f" page {block['page_number']}"
    return (
        f"<li>[{block['ref']}] {escape(block['document_filename'])}"
        f"{page} chunk {block['chunk_index']}: {escape(snippet(block['text'], 220))}</li>"
    )


def render_page(question: str = "", result: dict[str, Any] | None = None, debug: bool = False) -> str:
    stats = service.stats()
    documents = service.documents_payload()
    chunks = service.chunks_payload(limit=30)

    result_html = ""
    if result is not None:
        sources_html = "".join(format_source_item(item) for item in result["sources"])
        source_pages_html = "".join(f"<li>Page {page}</li>" for page in result.get("source_pages", []))
        context_html = "".join(format_context_item(block) for block in result.get("context", []))
        structured_html = ""
        if result.get("structured_answer") is not None:
            structured_html = f"""
            <h3>Structured output</h3>
            <pre>{escape(json.dumps(result["structured_answer"], indent=2, ensure_ascii=False))}</pre>
            """
        debug_html = ""
        if debug and result.get("debug") is not None:
            debug_html = f"""
            <h3>Debug information</h3>
            <pre>{escape(json.dumps(result["debug"], indent=2, ensure_ascii=False))}</pre>
            """
        result_html = f"""
        <section class="panel">
          <h2>Answer</h2>
          <pre>{escape(result["answer"])}</pre>
          <p class="small">Used LLM: {escape(str(result.get("used_llm", False)))}</p>
          {structured_html}
          {debug_html}
          <h3>Source pages</h3>
          <ul>{source_pages_html or "<li>No page matches</li>"}</ul>
          <h3>Retrieved context</h3>
          <ul>{context_html or "<li>No context available</li>"}</ul>
          <h3>Sources</h3>
          <ul>{sources_html or "<li>No sources</li>"}</ul>
        </section>
        """


    document_rows = "".join(
        f"<tr><td>{escape(doc['filename'])}</td><td>{escape(doc['source_type'])}</td>"
        f"<td>{doc['chunk_count']}</td><td>{doc.get('page_count') if doc.get('page_count') is not None else '-'}</td>"
        f"<td>{escape(doc['created_at'])}</td>"
        f"<td><form action=\"/documents/{escape(doc['id'])}/delete\" method=\"post\" style=\"display:inline;\">"
        f"<button type=\"submit\" class=\"secondary\">Delete</button></form></td></tr>"
        for doc in documents
    )

    chunk_rows = "".join(
        f"<tr><td>{escape(chunk['id'])}</td>"
        f"<td>{escape(chunk['document_filename'])}</td>"
        f"<td>{chunk['page_number'] if chunk['page_number'] is not None else '-'}</td>"
        f"<td>{chunk['chunk_index']}</td><td>{escape(snippet(chunk['text'], 180))}</td>"
        f"<td><form action=\"/chunks/{escape(chunk['id'])}/delete\" method=\"post\" style=\"display:inline;\">"
        f"<button type=\"submit\" class=\"secondary\">Delete</button></form></td></tr>"
        for chunk in chunks
    )

    question_value = escape(question)

    return f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <title>RAG Demo</title>
        <style>
          :root {{
            --bg: #0f172a;
            --panel: #111827;
            --panel-2: #1f2937;
            --text: #e5e7eb;
            --muted: #94a3b8;
            --accent: #38bdf8;
            --accent-2: #22c55e;
            --border: #334155;
          }}
          body {{
            margin: 0;
            font-family: Inter, Segoe UI, Arial, sans-serif;
            background: radial-gradient(circle at top, #1e293b, var(--bg));
            color: var(--text);
          }}
          .wrap {{ max-width: 1200px; margin: 0 auto; padding: 32px 20px 48px; }}
          h1 {{ margin: 0 0 8px; font-size: 34px; }}
          .sub {{ color: var(--muted); margin-bottom: 24px; }}
          .grid {{ display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 18px; }}
          .panel {{
            background: rgba(17, 24, 39, 0.9);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 18px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.22);
          }}
          label {{ display: block; font-weight: 600; margin: 12px 0 8px; }}
          input[type="text"] {{
            width: 100%; box-sizing: border-box; padding: 12px 14px;
            border-radius: 10px; border: 1px solid var(--border);
            background: #0b1220; color: var(--text);
          }}
          input[type="file"] {{ display: block; margin: 10px 0; }}
          button {{
            padding: 11px 16px; border: 0; border-radius: 10px;
            background: linear-gradient(135deg, var(--accent), #60a5fa);
            color: #05111f; font-weight: 700; cursor: pointer;
          }}
          button.secondary {{
            background: linear-gradient(135deg, var(--accent-2), #86efac);
            margin-left: 8px;
          }}
          table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
          th, td {{ border-bottom: 1px solid var(--border); padding: 10px 8px; text-align: left; vertical-align: top; }}
          th {{ color: #cbd5e1; font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em; }}
          pre {{
            white-space: pre-wrap;
            background: #0b1220;
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 14px;
            overflow: auto;
          }}
          .stats {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 18px; }}
          .stat {{
            padding: 12px 14px; border-radius: 12px; background: var(--panel-2);
            border: 1px solid var(--border); min-width: 120px;
          }}
          .stat strong {{ display: block; font-size: 22px; }}
          .small {{ color: var(--muted); font-size: 13px; }}
          a {{ color: var(--accent); }}
        </style>
      </head>
      <body>
        <div class="wrap">
          <h1>Retrieval-Augmented Generation Demo</h1>
          <div class="sub">Upload PDFs or text files, inspect stored chunks, and ask questions grounded in your own documents.</div>

          <div class="stats">
            <div class="stat"><strong>{stats["documents"]}</strong><span class="small">Documents</span></div>
            <div class="stat"><strong>{stats["chunks"]}</strong><span class="small">Chunks</span></div>
          </div>

          <div class="grid">
            <section class="panel">
              <h2>Upload documents</h2>
              <form action="/upload" method="post" enctype="multipart/form-data">
                <input type="file" name="files" multiple />
                <button type="submit">Ingest files</button>
              </form>

              <h2 style="margin-top:24px;">Ask a question</h2>
              <form action="/" method="get">
                <label for="question">Question</label>
                <input id="question" name="question" type="text" value="{question_value}" placeholder="What does the document say about refunds?" />
                <label style="margin-top:10px;">
                  <input type="checkbox" name="debug" value="true" {'checked' if debug else ''} />
                  Debug output
                </label>
                <div style="margin-top: 12px;">
                  <button type="submit">Search</button>
                </div>
              </form>
            </section>

            <section class="panel">
              <h2>API endpoints</h2>
              <ul>
                <li><a href="/documents">/documents</a></li>
                <li><a href="/chunks">/chunks</a></li>
                <li><a href="/health">/health</a></li>
              </ul>
              <p class="small">Use the JSON endpoints if you want to inspect the raw data directly.</p>
            </section>
          </div>

          {result_html}

          <section class="panel" style="margin-top:18px;">
            <h2>Stored documents</h2>
            <table>
              <thead>
                <tr>
                  <th>Filename</th>
                  <th>Type</th>
                  <th>Chunks</th>
                  <th>Pages</th>
                  <th>Created</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {document_rows or "<tr><td colspan='6'>No documents ingested yet.</td></tr>"}
              </tbody>
            </table>
          </section>

          <section class="panel" style="margin-top:18px;">
            <h2>Recent chunks</h2>
            <table>
              <thead>
                <tr>
                  <th>Chunk ID</th>
                  <th>Document</th>
                  <th>Page</th>
                  <th>Chunk</th>
                  <th>Preview</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {chunk_rows or "<tr><td colspan='6'>No chunks stored yet.</td></tr>"}
              </tbody>
            </table>
          </section>
        </div>
      </body>
    </html>
    """


@app.get("/", response_class=HTMLResponse)
def home(question: str = "", debug: bool = False) -> HTMLResponse:
    result = service.answer(question, debug=debug) if question.strip() else None
    return HTMLResponse(render_page(question=question, result=result, debug=debug))


@app.post("/upload")
def upload(files: list[UploadFile] = File(...)) -> RedirectResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    service.ingest_uploads(files)
    return RedirectResponse(url="/", status_code=303)


@app.post("/documents/{document_id}/delete")
def delete_document(document_id: str) -> RedirectResponse:
    service.delete_document(document_id)
    return RedirectResponse(url="/", status_code=303)


@app.post("/chunks/{chunk_id}/delete")
def delete_chunk(chunk_id: str) -> RedirectResponse:
    service.delete_chunk(chunk_id)
    return RedirectResponse(url="/", status_code=303)


@app.get("/documents")
def documents() -> JSONResponse:
    return JSONResponse(
        {
            "stats": service.stats(),
            "documents": service.documents_payload(),
        }
    )


@app.get("/chunks")
def chunks(limit: int = 100) -> JSONResponse:
    return JSONResponse(
        {
            "stats": service.stats(),
            "chunks": service.chunks_payload(limit=limit),
        }
    )


@app.delete("/documents/{document_id}")
def delete_document_api(document_id: str) -> JSONResponse:
    return JSONResponse(service.delete_document(document_id))


@app.delete("/chunks/{chunk_id}")
def delete_chunk_api(chunk_id: str) -> JSONResponse:
    return JSONResponse(service.delete_chunk(chunk_id))


@app.get("/documents/{document_id}")
def document_detail(document_id: str) -> JSONResponse:
    payload = service.document_payload(document_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return JSONResponse(payload)


@app.get("/documents/{document_id}/debug")
def document_debug(document_id: str) -> JSONResponse:
    payload = service.document_debug(document_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return JSONResponse(payload)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/query")
def query(question: str = Form(...), top_k: int = Form(4), debug: bool = Form(False)) -> JSONResponse:
    return JSONResponse(service.answer(question, top_k=top_k, debug=debug))


@app.post("/batch-query")
def batch_query(questions: list[str] = Body(...), top_k: int = 4, debug: bool = False) -> JSONResponse:
    return JSONResponse(service.answer_batch(questions, top_k=top_k, debug=debug))
