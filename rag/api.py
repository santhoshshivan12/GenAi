from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from rag.service import RAGService
from rag.config import TRACE_FILE
from rag.utils import snippet

app = FastAPI(title="RAG Demo - Week 4 Hybrid Evaluation", version="2.0.0")
service = RAGService()

# Load Week 4 Golden Set if available
GOLDEN_SET: list[dict[str, Any]] = []
golden_path = Path("week4/golden_set.json")
if golden_path.exists():
    try:
        GOLDEN_SET = json.loads(golden_path.read_text(encoding="utf-8"))
    except Exception:
        GOLDEN_SET = []

# Map of question ID/text to fixed status
FIXED_IDS = {"Q01", "Q05", "Q06", "Q07", "Q08", "Q09", "Q11"}
AFTER_RESULTS_FILE = Path("week4/after_results.json")


def get_benchmark_metrics() -> dict[str, Any]:
    total_q = len(GOLDEN_SET) or 12
    fixed_q = len(FIXED_IDS) or 7
    rate_pct = round((fixed_q / total_q) * 100, 2) if total_q else 58.33
    if AFTER_RESULTS_FILE.exists():
        try:
            res = json.loads(AFTER_RESULTS_FILE.read_text(encoding="utf-8"))
            total_q = res.get("total_questions", total_q)
            fixed_q = res.get("hits_at_3", fixed_q)
            rate_pct = res.get("hit_at_3_rate_pct", rate_pct)
        except Exception:
            pass
    return {
        "total_questions": total_q,
        "fixed_questions": fixed_q,
        "hit_at_3_rate_pct": rate_pct,
        "is_ship": rate_pct >= 50.0,
    }


def format_source_item(item: dict[str, Any]) -> str:
    filename = item.get("filename") or item.get("document_filename") or "Unknown"
    page_num = item.get("page_number")
    page = "" if page_num is None else f" page {page_num}"
    chunk_index = item.get("chunk_index", 0)
    score = item.get("score", 0.0)
    rrf = f" (RRF: {item['rrf_score']})" if "rrf_score" in item else ""
    return (
        f"<li><strong>{escape(str(filename))}</strong>"
        f"{page} chunk {chunk_index} — score {score}{rrf}</li>"
    )


def format_context_item(block: dict[str, Any]) -> str:
    page = "" if block.get("page_number") is None else f" page {block['page_number']}"
    score_info = f"score: {block.get('score', 0.0)}"
    if block.get("rrf_score"):
        score_info = f"RRF: {block['rrf_score']}"
    return (
        f"<li>[{block.get('ref', 1)}] {escape(str(block.get('document_filename', 'Doc')))}"
        f"{page} chunk {block.get('chunk_index', 0)} ({score_info}): "
        f"<code>{escape(snippet(block.get('text', ''), 200))}</code></li>"
    )


def render_comparison_view(comparison: dict[str, Any]) -> str:
    golden = comparison.get("golden_item")
    expected_chunk_id = comparison.get("expected_chunk_id")
    baseline = comparison.get("baseline", {})
    hybrid = comparison.get("hybrid", {})

    golden_banner = ""
    if golden:
        is_fixed = golden.get("id") in FIXED_IDS
        status_tag = (
            '<span class="badge badge-success">🚀 FIXED BY HYBRID RRF</span>'
            if is_fixed
            else '<span class="badge badge-warning">⚠️ Still Broken (Low TF)</span>'
        )
        exact_badge = (
            '<span class="badge badge-purple">Exact Code Token Query</span>'
            if golden.get("is_exact_token")
            else '<span class="badge badge-info">Natural Language Query</span>'
        )
        golden_banner = f"""
        <div class="golden-banner">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <div>
              <span class="badge badge-cyan">Golden Set {escape(golden.get('id', ''))}</span>
              {status_tag}
              {exact_badge}
            </div>
            <div class="small">
              Source: <strong>{escape(golden.get('source_file', ''))}</strong> | 
              Target Chunk: <code>{escape(golden.get('correct_chunk_id', '')[:12])}...</code>
            </div>
          </div>
        </div>
        """

    def render_column(data: dict[str, Any], mode_type: str) -> str:
        hits = data.get("hits", [])
        hit_at_3 = data.get("hit_at_3")
        target_rank = data.get("target_rank")
        latency = data.get("latency_ms", 0.0)

        if hit_at_3 is True:
            badge = f'<span class="badge badge-success">✅ HIT@3 (Rank #{target_rank})</span>'
            header_class = "card-header success-header"
        elif hit_at_3 is False:
            badge = '<span class="badge badge-danger">❌ MISS (Rank > 3)</span>'
            header_class = "card-header danger-header"
        else:
            badge = '<span class="badge badge-info">Retrieved Top-3</span>'
            header_class = "card-header"

        if mode_type == "hybrid":
            title = "🚀 Week 4 Hybrid (BM25 + RRF)"
        elif mode_type == "multiquery":
            title = "🔀 Multi-Query (3x Top-4) + BM25"
        else:
            title = "🐢 Baseline (Dense Vector Only)"

        if expected_chunk_id:
            if target_rank is not None:
                if target_rank <= 3:
                    rank_callout = f"""
                    <div class="rank-callout rank-hit">
                      🎯 Target Chunk: <strong>Rank #{target_rank}</strong> &mdash; <em>Top-3 Hit!</em>
                    </div>
                    """
                else:
                    rank_callout = f"""
                    <div class="rank-callout rank-miss">
                      📍 Target Chunk: <strong>Rank #{target_rank}</strong> &mdash; <em>Outside Top-3</em>
                    </div>
                    """
            else:
                rank_callout = """
                <div class="rank-callout rank-miss">
                  📍 Target Chunk: <strong>Absent from Candidates</strong>
                </div>
                """
        else:
            rank_callout = ""

        # For multiquery mode, render variation pill tags
        variations_html = ""
        if mode_type == "multiquery" and data.get("variations"):
            vars_list = "".join(f"<li><code>{escape(v)}</code></li>" for v in data.get("variations", []))
            variations_html = f"""
            <div style="background:#070d18; border:1px solid var(--border); border-radius:8px; padding:10px; margin-bottom:12px; font-size:12px;">
              <div style="font-weight:700; color:var(--accent); margin-bottom:4px;">3 Generated Query Variations (3x4 retrieval):</div>
              <ul style="margin:0; padding-left:18px;">{vars_list}</ul>
              <div class="small" style="margin-top:6px; color:var(--muted);">Candidate Pool: <strong>{data.get('candidate_pool_size', 0)} unique chunks</strong> gathered & BM25 re-ranked</div>
            </div>
            """

        chunks_html = ""
        for rank, hit in enumerate(hits, start=1):
            c_id = hit.get("id", "")
            is_target = expected_chunk_id and c_id == expected_chunk_id
            target_class = "chunk-card target-match" if is_target else "chunk-card"
            target_pill = '<span class="pill-target">🎯 TARGET CHUNK MATCH</span>' if is_target else ""

            score_pills = []
            if mode_type == "hybrid":
                if hit.get("rrf_score"):
                    score_pills.append(f'<span class="score-pill">RRF: {hit["rrf_score"]}</span>')
                if hit.get("bm25_score") is not None:
                    score_pills.append(f'<span class="score-pill score-bm25">BM25: {hit["bm25_score"]}</span>')
                if hit.get("dense_score") is not None:
                    score_pills.append(f'<span class="score-pill score-dense">Dense: {hit["dense_score"]:.3f}</span>')
            elif mode_type == "multiquery":
                if hit.get("bm25_rerank_score") is not None:
                    score_pills.append(f'<span class="score-pill score-bm25">BM25 Re-rank: {hit["bm25_rerank_score"]}</span>')
                if hit.get("score") is not None:
                    score_pills.append(f'<span class="score-pill score-dense">Vector: {hit.get("score", 0.0):.3f}</span>')
            else:
                score_pills.append(f'<span class="score-pill score-dense">Cosine: {hit.get("score", 0.0):.4f}</span>')

            scores_str = " ".join(score_pills)
            filename = hit.get("document_filename") or hit.get("source_file") or "Document"
            page_part = f"p.{hit.get('page_number')}" if hit.get("page_number") is not None else ""

            chunks_html += f"""
            <div class="{target_class}">
              <div class="chunk-header">
                <div><strong>#{rank}</strong> {escape(filename)} <span class="small">{page_part}</span></div>
                <div>{target_pill} {scores_str}</div>
              </div>
              <div class="chunk-text">{escape(snippet(hit.get('text', ''), 240))}</div>
              <div class="chunk-meta">ID: <code>{escape(c_id[:16])}...</code></div>
            </div>
            """

        answer_box = f"""
        <div class="answer-box">
          <div class="small" style="margin-bottom:6px; color:var(--muted); font-weight:600;">Grounded Synthesis:</div>
          <pre>{escape(data.get("answer", "No answer generated."))}</pre>
        </div>
        """

        return f"""
        <div class="compare-column panel">
          <div class="{header_class}">
            <div>
              <h3>{title}</h3>
              <span class="latency-tag">⏱️ {latency} ms</span>
            </div>
            <div>{badge}</div>
          </div>
          <div style="padding-top:14px;">
            {rank_callout}
            {variations_html}
            <div class="sub-title">Top 3 Retrieved Chunks:</div>
            {chunks_html or "<p class='small'>No chunks retrieved</p>"}
            {answer_box}
          </div>
        </div>
        """

    multiquery = comparison.get("multiquery", {})

    return f"""
    <section class="panel" style="margin-top:20px;">
      <h2 style="margin-bottom:12px;">⚖️ 3-Way Retrieval Architecture Comparison</h2>
      <p class="small" style="margin-bottom:14px;">
        Question: <strong>&ldquo;{escape(comparison.get('question', ''))}&rdquo;</strong>
      </p>
      {golden_banner}
      <div class="compare-grid" style="grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));">
        {render_column(baseline, mode_type="dense")}
        {render_column(hybrid, mode_type="hybrid")}
        {render_column(multiquery, mode_type="multiquery")}
      </div>
    </section>
    """


def render_chat_view(question: str, result: dict[str, Any] | None, top_k: int) -> str:
    messages = """
      <div class="chat-message assistant-message">
        <div class="chat-role">RAG Assistant</div>
        <p>Ask a question about your indexed documents. I combine semantic similarity and BM25 keyword retrieval, re-rank the merged candidates, and answer only from the returned chunks.</p>
      </div>
    """
    if result is not None:
        source_items = "".join(
            f"<li>{escape(str(item.get('filename') or item.get('document_filename') or 'Unknown'))} ? chunk {item.get('chunk_index', 0)}</li>"
            for item in result.get("sources", [])
        )
        messages += f"""
          <div class="chat-message user-message"><div class="chat-role">You</div><p>{escape(question)}</p></div>
          <div class="chat-message assistant-message">
            <div class="chat-role">RAG Assistant</div>
            <pre>{escape(result.get('answer', ''))}</pre>
            <details class="chat-sources"><summary>Retrieved sources ({len(result.get('chunks', []))})</summary><ul>{source_items or '<li>No sources returned</li>'}</ul></details>
          </div>
        """

    selected_top_k = lambda value: "selected" if top_k == value else ""
    return f"""
      <section class="chat-shell">
        <div class="chat-toolbar">
          <div><strong>Hybrid RAG Chat</strong><span>Semantic + BM25 keyword retrieval ? RRF re-rank</span></div>
          <div class="retrieval-status">Top 25 semantic + Top 25 BM25 ? Top {top_k}</div>
        </div>
        <div class="chat-messages">{messages}</div>
        <form action="/" method="get" class="chat-input-form">
          <input type="hidden" name="tab" value="chat" />
          <input type="hidden" name="retrieval_mode" value="hybrid" />
          <input name="question" type="text" value="{escape(question)}" placeholder="Ask about the indexed documents?" required autofocus />
          <label for="chat-top-k">Top N</label>
          <select id="chat-top-k" name="top_k">
            <option value="3" {selected_top_k(3)}>3</option><option value="4" {selected_top_k(4)}>4</option><option value="5" {selected_top_k(5)}>5</option>
          </select>
          <button type="submit">Send</button>
        </form>
      </section>
    """

def render_page(
    result: dict[str, Any] | None = None,
    question: str = "",
    active_tab: str = "chat",
    top_k: int = 3,
    comparison: dict[str, Any] | None = None,
    retrieval_mode: str = "compare",
    debug: bool = False,
) -> str:
    stats = service.stats()
    documents = service.documents_payload()
    chunks = service.chunks_payload(limit=25)
    metrics = get_benchmark_metrics()
    trace_ids = []
    if TRACE_FILE.exists():
        for line in TRACE_FILE.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
                if item.get("trace_id") and item["trace_id"] not in trace_ids:
                    trace_ids.append(item["trace_id"])
            except json.JSONDecodeError:
                continue
    trace_options = "".join("<option value=\"" + escape(t) + "\">" + escape(t) + "</option>" for t in trace_ids)

    comparison_html = ""
    if comparison is not None:
        comparison_html = render_comparison_view(comparison)

    single_result_html = ""
    if result is not None and comparison is None and active_tab == "evaluation":
        sources_html = "".join(format_source_item(item) for item in result.get("sources", []))
        context_html = "".join(format_context_item(block) for block in result.get("context", []))
        trace_id = result.get("trace_id", "Not recorded")
        debug_data = result.get("debug", {})
        retrieval_debug = debug_data.get("retrieval", {})
        trace_details = ""
        if debug:
            trace_details = f"""
            <p class="small">Prompt version: <code>rag-answer-v1</code> · Search query: <code>{escape(str(retrieval_debug.get('tool_query', result.get('question', ''))))}</code></p>
            <p class="small">Retrieved chunks recorded: {len(retrieval_debug.get('hits', result.get('chunks', [])))}</p>
            """
        single_result_html = f"""
        <section class="panel" style="margin-top:20px;">
          <h2>Grounded Answer ({escape(retrieval_mode.upper())} Mode)</h2>
          <pre>{escape(result.get("answer", ""))}</pre>
          <p class="small">Used LLM: {escape(str(result.get("used_llm", False)))}</p>
          <div class="trace-card">
            <strong>Week 5 Trace</strong>
            <span class="small">Trace ID: <code>{escape(str(trace_id))}</code></span>
            <span class="small">Saved to <code>data/traces.jsonl</code> · replayable from the trace alone</span>
            {trace_details}
          </div>
          <h3 style="margin-top:14px;">Retrieved context blocks</h3>
          <ul>{context_html or "<li>No context available</li>"}</ul>
          <h3 style="margin-top:14px;">Sources</h3>
          <ul>{sources_html or "<li>No sources</li>"}</ul>
        </section>
        """

    golden_rows = ""
    for item in GOLDEN_SET:
        q_id = item.get("id", "")
        q_text = item.get("question", "")
        q_src = item.get("source_file", "")
        is_fixed = q_id in FIXED_IDS

        status_badge = (
            '<span class="badge badge-success">Fixed 🟢</span>'
            if is_fixed
            else '<span class="badge badge-danger">Miss ❌</span>'
        )
        token_badge = (
            '<span class="badge badge-purple">Exact Symbol</span>'
            if item.get("is_exact_token")
            else '<span class="badge badge-info">NL</span>'
        )

        q_enc = escape(q_text)
        golden_rows += f"""
        <tr>
          <td><strong>{escape(q_id)}</strong></td>
          <td>
            <div>{escape(q_text)}</div>
            <div class="small" style="color:var(--muted);">{escape(q_src)} &bull; {token_badge}</div>
          </td>
          <td><span class="badge badge-danger">Miss (0%) ❌</span></td>
          <td>{status_badge}</td>
          <td>
            <a href="/?question={q_enc}&retrieval_mode=compare" class="btn-test">⚡ Run Comparison</a>
          </td>
        </tr>
        """

    document_rows = "".join(
        f"<tr><td>{escape(doc['filename'])}</td><td>{escape(doc['source_type'])}</td>"
        f"<td>{escape(doc.get('chunk_strategy', 'fixed_size'))}</td>"
        f"<td>{doc['chunk_count']}</td><td>{doc.get('page_count') if doc.get('page_count') is not None else '-'}</td>"
        f"<td>{escape(doc['created_at'])}</td>"
        f"<td><form action=\"/documents/{escape(doc['id'])}/delete\" method=\"post\" style=\"display:inline;\">"
        f"<button type=\"submit\" class=\"btn-danger-small\">Delete</button></form></td></tr>"
        for doc in documents
    )

    chunk_rows = "".join(
        f"<tr><td><code>{escape(chunk['id'][:12])}...</code></td>"
        f"<td>{escape(chunk['document_filename'])}</td>"
        f"<td>{escape(chunk.get('chunk_strategy', 'fixed_size'))}</td>"
        f"<td>{chunk['page_number'] if chunk['page_number'] is not None else '-'}</td>"
        f"<td>{chunk['chunk_index']}</td>"
        f"<td>{chunk.get('word_count') if chunk.get('word_count') is not None else '-'}</td>"
        f"<td>{escape(snippet(chunk['text'], 150))}</td>"
        f"<td><form action=\"/chunks/{escape(chunk['id'])}/delete\" method=\"post\" style=\"display:inline;\">"
        f"<button type=\"submit\" class=\"btn-danger-small\">Delete</button></form></td></tr>"
        for chunk in chunks
    )

    question_value = escape(question)

    chat_html = render_chat_view(question, result if active_tab == "chat" else None, top_k)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>RAG Evaluation Demo — Week 4 Hybrid Search</title>
    <style>
      :root {{
        --bg: #0b0f19;
        --panel: #111827;
        --panel-2: #1e293b;
        --panel-hover: #243248;
        --text: #f1f5f9;
        --muted: #94a3b8;
        --accent: #38bdf8;
        --accent-glow: rgba(56, 189, 248, 0.25);
        --success: #10b981;
        --success-glow: rgba(16, 185, 129, 0.25);
        --danger: #ef4444;
        --purple: #a855f7;
        --border: #334155;
        --border-light: rgba(255, 255, 255, 0.1);
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        background: radial-gradient(circle at 50% 0%, #172554 0%, var(--bg) 60%);
        color: var(--text);
        line-height: 1.5;
        min-height: 100vh;
      }}
      .wrap {{ max-width: 1300px; margin: 0 auto; padding: 28px 20px 60px; }}
      
      /* Headers & Title */
      .header {{ margin-bottom: 24px; }}
      h1 {{ margin: 0 0 6px; font-size: 32px; font-weight: 800; letter-spacing: -0.02em; }}
      h1 span {{ color: var(--accent); }}
      .sub {{ color: var(--muted); font-size: 15px; }}

      /* Metric Ribbon */
      .metrics-banner {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 14px;
        margin-bottom: 24px;
      }}
      .metric-card {{
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 16px 18px;
        position: relative;
        overflow: hidden;
      }}
      .metric-card.highlight {{
        border-color: var(--success);
        box-shadow: 0 0 20px var(--success-glow);
      }}
      .metric-title {{ font-size: 13px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; }}
      .metric-value {{ font-size: 28px; font-weight: 800; margin: 4px 0 2px; }}
      .metric-delta {{ font-size: 12px; font-weight: 600; }}
      .text-success {{ color: var(--success); }}
      .text-danger {{ color: var(--danger); }}
      .text-cyan {{ color: var(--accent); }}

      /* Panels */
      .panel {{
        background: rgba(17, 24, 39, 0.95);
        backdrop-filter: blur(10px);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.35);
      }}
      .trace-card {{
        display: flex;
        flex-direction: column;
        gap: 5px;
        margin: 14px 0;
        padding: 12px;
        border: 1px solid rgba(56, 189, 248, 0.35);
        border-radius: 10px;
        background: rgba(14, 116, 144, 0.12);
      }}
      h2 {{ margin: 0 0 14px; font-size: 20px; font-weight: 700; color: #f8fafc; }}
      h3 {{ margin: 0 0 10px; font-size: 16px; font-weight: 700; }}
      .sub-title {{ font-size: 13px; font-weight: 700; text-transform: uppercase; color: var(--muted); margin-bottom: 10px; }}

      /* Search & Form Elements */
      .search-form {{ display: flex; flex-direction: column; gap: 14px; }}
      .input-row {{ display: flex; gap: 10px; }}
      input[type="text"], select, input[type="number"] {{
        width: 100%; padding: 12px 16px;
        border-radius: 10px; border: 1px solid var(--border);
        background: #070d18; color: var(--text); font-size: 15px;
      }}
      input[type="text"]:focus, select:focus {{
        outline: none; border-color: var(--accent);
        box-shadow: 0 0 0 3px var(--accent-glow);
      }}
      .mode-pills {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 4px; }}
      .mode-pill-label {{
        display: flex; align-items: center; gap: 6px; padding: 8px 14px;
        background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px;
        cursor: pointer; font-size: 13px; font-weight: 600;
      }}
      .mode-pill-label:hover {{ background: var(--panel-hover); }}
      .mode-pill-label input {{ margin: 0; }}

      button, .btn-test {{
        padding: 12px 20px; border: 0; border-radius: 10px;
        background: linear-gradient(135deg, var(--accent), #2563eb);
        color: #ffffff; font-weight: 700; cursor: pointer;
        text-decoration: none; display: inline-flex; align-items: center; justify-content: center;
        transition: transform 0.1s ease, box-shadow 0.1s ease;
      }}
      button:hover, .btn-test:hover {{
        transform: translateY(-1px);
        box-shadow: 0 6px 16px var(--accent-glow);
      }}
      .btn-test {{
        padding: 6px 12px; font-size: 12px; border-radius: 6px;
        background: linear-gradient(135deg, #0284c7, #0369a1);
      }}
      .btn-danger-small {{
        padding: 4px 8px; font-size: 11px; border-radius: 4px;
        background: #dc2626; color: white; border: 0; cursor: pointer;
      }}

      /* Comparison UI */
      .compare-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-top: 16px; }}
      @media (max-width: 900px) {{ .compare-grid {{ grid-template-columns: 1fr; }} }}
      
      .compare-column {{ border-top: 4px solid var(--border); }}
      .card-header {{
        display: flex; justify-content: space-between; align-items: center;
        padding-bottom: 14px; border-bottom: 1px solid var(--border);
      }}
      .card-header.success-header {{ border-top-color: var(--success); }}
      .card-header.danger-header {{ border-top-color: var(--danger); }}
      .latency-tag {{ font-size: 12px; color: var(--muted); background: #070d18; padding: 3px 8px; border-radius: 6px; }}

      .chunk-card {{
        background: #070d18; border: 1px solid var(--border);
        border-radius: 10px; padding: 12px; margin-bottom: 10px;
      }}
      .chunk-card.target-match {{
        border: 1px solid var(--success);
        background: rgba(16, 185, 129, 0.08);
        box-shadow: 0 0 14px var(--success-glow);
      }}
      .chunk-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-size: 13px; }}
      .chunk-text {{ font-size: 13px; color: #cbd5e1; font-family: monospace; background: rgba(0,0,0,0.25); padding: 8px; border-radius: 6px; }}
      .chunk-meta {{ font-size: 11px; color: var(--muted); margin-top: 6px; }}

      .score-pill {{
        display: inline-block; font-size: 11px; padding: 2px 6px; border-radius: 4px;
        background: var(--panel-2); font-weight: 600;
      }}
      .score-bm25 {{ color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.3); }}
      .score-dense {{ color: var(--accent); border: 1px solid rgba(56, 189, 248, 0.3); }}
      .pill-target {{
        display: inline-block; font-size: 11px; padding: 2px 6px; border-radius: 4px;
        background: var(--success); color: #022c22; font-weight: 800;
      }}

      .rank-callout {{
        padding: 10px 14px; border-radius: 8px; font-size: 13px; margin-bottom: 14px; font-weight: 600;
        display: flex; align-items: center; justify-content: space-between;
      }}
      .rank-callout.rank-hit {{
        background: rgba(16, 185, 129, 0.15); border: 1px solid var(--success); color: #34d399;
      }}
      .rank-callout.rank-miss {{
        background: rgba(239, 68, 68, 0.15); border: 1px solid var(--danger); color: #fca5a5;
      }}

      .answer-box {{
        margin-top: 14px; background: #070d18; border: 1px solid var(--border);
        border-radius: 10px; padding: 14px;
      }}
      pre {{
        white-space: pre-wrap; margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 14px; line-height: 1.5; color: #e2e8f0;
      }}

      /* Badges */
      .badge {{
        display: inline-block; font-size: 11px; font-weight: 700; padding: 3px 8px;
        border-radius: 6px; text-transform: uppercase; letter-spacing: 0.04em;
      }}
      .badge-success {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.4); }}
      .badge-danger {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(248, 113, 113, 0.4); }}
      .badge-cyan {{ background: rgba(56, 189, 248, 0.2); color: var(--accent); border: 1px solid rgba(56, 189, 248, 0.4); }}
      .badge-purple {{ background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid rgba(192, 132, 252, 0.4); }}
      .badge-info {{ background: rgba(148, 163, 184, 0.2); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.4); }}
      .badge-warning {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }}

      .golden-banner {{
        background: rgba(15, 23, 42, 0.8); border: 1px solid var(--border);
        border-radius: 10px; padding: 12px 16px; margin-bottom: 14px;
      }}

      /* Tables */
      .tabs {{ display:flex; gap:8px; margin:22px 0 18px; border-bottom:1px solid var(--border); }}
      .tab-link {{ padding:10px 16px; color:var(--muted); border-bottom:2px solid transparent; font-weight:700; }}
      .tab-link.active {{ color:var(--accent); border-color:var(--accent); }}
      .tab-panel {{ display:none; }}
      .tab-panel.active {{ display:block; }}
      .chat-shell {{ max-width:900px; margin:0 auto; background:var(--panel); border:1px solid var(--border); border-radius:14px; overflow:hidden; }}
      .chat-toolbar {{ padding:16px 18px; display:flex; justify-content:space-between; gap:14px; align-items:center; background:var(--panel-2); border-bottom:1px solid var(--border); }}
      .chat-toolbar strong, .chat-toolbar span {{ display:block; }}
      .chat-toolbar span {{ font-size:12px; color:var(--muted); margin-top:4px; }}
      .retrieval-status {{ color:var(--success); font-size:12px; font-weight:700; text-align:right; }}
      .chat-messages {{ min-height:390px; padding:20px; display:flex; flex-direction:column; gap:14px; background:#0d1422; }}
      .chat-message {{ max-width:85%; padding:13px 15px; border-radius:12px; line-height:1.55; }}
      .assistant-message {{ align-self:flex-start; background:var(--panel-2); border:1px solid var(--border); }}
      .user-message {{ align-self:flex-end; background:#075985; }}
      .chat-role {{ font-size:11px; font-weight:800; text-transform:uppercase; letter-spacing:.06em; color:var(--accent); margin-bottom:6px; }}
      .user-message .chat-role {{ color:#e0f2fe; }}
      .chat-message p {{ margin:0; }}
      .chat-message pre {{ white-space:pre-wrap; font-family:inherit; margin:0; }}
      .chat-sources {{ margin-top:12px; color:var(--muted); font-size:12px; }}
      .chat-input-form {{ display:flex; gap:9px; padding:14px; border-top:1px solid var(--border); background:var(--panel); }}
      .chat-input-form input {{ flex:1; }}
      .chat-input-form select {{ width:auto; }}
      .chat-input-form label {{ white-space:nowrap; align-self:center; color:var(--muted); font-size:12px; }}
      @media (max-width:700px) {{ .chat-toolbar, .chat-input-form {{ flex-wrap:wrap; }} .chat-message {{ max-width:100%; }} .chat-input-form input {{ min-width:100%; }} }}
      table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }}
      th, td {{ border-bottom: 1px solid var(--border); padding: 10px 10px; text-align: left; vertical-align: middle; }}
      th {{ color: var(--muted); text-transform: uppercase; font-size: 11px; letter-spacing: 0.05em; font-weight: 700; }}
      tr:hover td {{ background: rgba(255, 255, 255, 0.02); }}

      .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-top: 20px; }}
      @media (max-width: 900px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
      .small {{ font-size: 12px; color: var(--muted); }}
      code {{ font-family: monospace; background: #070d18; padding: 2px 5px; border-radius: 4px; color: #38bdf8; }}
      a {{ color: var(--accent); text-decoration: none; }}
    </style>
  </head>
  <body>
    <div class="wrap">
      
      <!-- Top Title & Navigation -->
      <div class="header">
        <h1>Retrieval-Augmented Generation <span>Evaluation Demo</span></h1>
        <div class="sub">Week 4 Practical — Task Set E: Benchmark, Inspection & Hybrid Retrieval (BM25 + RRF)</div>
      </div>

      <!-- Metric Ribbon -->
      <nav class="tabs" aria-label="Application sections">
        <a class="tab-link {'active' if active_tab == 'chat' else ''}" href="/?tab=chat">Chat</a>
        <a class="tab-link {'active' if active_tab == 'evaluation' else ''}" href="/?tab=evaluation">Evaluation</a>
        <a class="tab-link {'active' if active_tab == 'trace_review' else ''}" href="/?tab=trace_review">Trace Review</a>
      </nav>
      <section class="tab-panel {'active' if active_tab == 'chat' else ''}">{chat_html}</section>
      <section class="tab-panel {'active' if active_tab == 'trace_review' else ''}"><section class="panel"><h2>Trace Review</h2><p class="small">Enter a trace ID to have the configured LLM review it and append the result to <code>week5/notes.md</code>.</p><form action="/trace-review" method="post" class="search-form"><select name="trace_id"><option value="">Select a complete trace ID</option>{trace_options}</select><button type="submit">Review Trace</button><button type="submit" name="trace_id" value="auto">Review Random Trace</button></form></section></section>
<section class="tab-panel {'active' if active_tab == 'evaluation' else ''}">
      <div class="metrics-banner">
        <div class="metric-card">
          <div class="metric-title">Baseline Hit@3 (Dense)</div>
          <div class="metric-value text-danger">0.0%</div>
          <div class="metric-delta text-danger">0 / {metrics['total_questions']} Target Chunks</div>
        </div>
        <div class="metric-card highlight">
          <div class="metric-title">Week 4 Hit@3 (Hybrid RRF)</div>
          <div class="metric-value text-success">{metrics['hit_at_3_rate_pct']:.2f}%</div>
          <div class="metric-delta text-success">{metrics['fixed_questions']} / {metrics['total_questions']} Target Chunks (+{metrics['hit_at_3_rate_pct']:.2f}%)</div>
        </div>
        <div class="metric-card">
          <div class="metric-title">Retrieval Failures Fixed</div>
          <div class="metric-value text-cyan">{metrics['fixed_questions']} / {metrics['total_questions']}</div>
          <div class="metric-delta text-cyan">Lexical Overlap Resolved</div>
        </div>
        <div class="metric-card highlight">
          <div class="metric-title">Shipping Decision</div>
          <div class="metric-value text-success">{'SHIP ✅' if metrics['is_ship'] else 'NO SHIP ❌'}</div>
          <div class="metric-delta text-success">{'Passes Quality Bar (≥50%)' if metrics['is_ship'] else 'Below Quality Bar (<50%)'}</div>
        </div>
      </div>

      <!-- Live Search Box -->
      <section class="panel">
        <h2>🔍 Test RAG Retrieval live</h2>
        <form action="/" method="get" class="search-form">
          <div class="input-row">
            <input id="question" name="question" type="text" value="{question_value}" placeholder="Enter question or pick one from the Golden Set below..." required />
            <button type="submit">Run Query</button>
          </div>
          
          <div>
            <div class="small" style="font-weight:600; margin-bottom:6px;">Retrieval Mode:</div>
            <div class="mode-pills">
              <label class="mode-pill-label">
                <input type="radio" name="retrieval_mode" value="compare" {'checked' if retrieval_mode == 'compare' else ''} />
                <span>⚖️ 3-Way Architecture Comparison (Baseline vs. Hybrid vs. Multi-Query)</span>
              </label>
              <label class="mode-pill-label">
                <input type="radio" name="retrieval_mode" value="multiquery" {'checked' if retrieval_mode == 'multiquery' else ''} />
                <span>🔀 Multi-Query (3x Top-4) + BM25</span>
              </label>
              <label class="mode-pill-label">
                <input type="radio" name="retrieval_mode" value="hybrid" {'checked' if retrieval_mode == 'hybrid' else ''} />
                <span>🚀 Week 4 Hybrid (BM25 + RRF)</span>
              </label>
              <label class="mode-pill-label">
                <input type="radio" name="retrieval_mode" value="dense" {'checked' if retrieval_mode == 'dense' else ''} />
                <span>🐢 Baseline (Dense Vector Only)</span>
              </label>
            </div>
          </div>
        </form>
      </section>

      <!-- Side-by-Side Comparison Result -->
      {comparison_html}

      <!-- Single Result (if not comparison) -->
      {single_result_html}

      <!-- Week 4 Golden Set Interactive Benchmark Panel -->
      <section class="panel" style="margin-top:20px;">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
          <div>
            <h2>📋 Week 4 Golden Set Ground Truth Benchmark (12 Questions)</h2>
            <div class="small">Click <strong>&ldquo;⚡ Run Comparison&rdquo;</strong> on any question below to see the exact before vs. after retrieval difference live on screen.</div>
          </div>
        </div>

        <table>
          <thead>
            <tr>
              <th style="width:50px;">ID</th>
              <th>Question & Target Document</th>
              <th>Baseline (Dense)</th>
              <th>Week 4 (Hybrid RRF)</th>
              <th style="width:140px;">Live Action</th>
            </tr>
          </thead>
          <tbody>
            {golden_rows or "<tr><td colspan='5'>Golden set not loaded.</td></tr>"}
          </tbody>
        </table>
      </section>

      <!-- Ingestion & Data Management Grid -->
      <div class="grid-2">
        <!-- Ingestion Form -->
        <section class="panel">
          <h2>📤 Upload & Index Documents</h2>
          <form action="/upload" method="post" enctype="multipart/form-data">
            <input type="file" name="files" multiple required />
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:10px;">
              <div>
                <label class="small" for="chunk_strategy">Strategy</label>
                <select id="chunk_strategy" name="chunk_strategy">
                  <option value="structure_aware">Structure-Aware</option>
                  <option value="fixed_size">Fixed-Size Overlap</option>
                  <option value="sentence">Sentence Structural</option>
                </select>
              </div>
              <div>
                <label class="small" for="chunk_size">Chunk Size</label>
                <input id="chunk_size" name="chunk_size" type="number" value="300" min="10" max="2000" />
              </div>
            </div>
            <div style="margin-top:12px; display:flex; justify-content:space-between; align-items:center;">
              <button type="submit">Ingest Files</button>
            </div>
          </form>
        </section>

        <!-- Stored Documents -->
        <section class="panel">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <h2>📁 Ingested Documents ({stats['documents']})</h2>
            <form action="/clear" method="post" onsubmit="return confirm('Clear ALL documents and chunks?');">
              <button type="submit" class="btn-danger-small">Clear All</button>
            </form>
          </div>
          <table style="font-size:12px;">
            <thead>
              <tr>
                <th>Filename</th>
                <th>Chunks</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {document_rows or "<tr><td colspan='3'>No documents ingested yet.</td></tr>"}
            </tbody>
          </table>
        </section>
      </div>

      <!-- Recent Chunks -->
      <section class="panel" style="margin-top:20px;">
        <h2>🧩 Indexed Chunks Explorer ({stats['chunks']} total)</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Document</th>
              <th>Strategy</th>
              <th>Page</th>
              <th>Index</th>
              <th>Words</th>
              <th>Preview</th>
              <th>Action</th>
            </tr>
          </thead>
      </section>
          <tbody>
            {chunk_rows or "<tr><td colspan='8'>No chunks stored yet.</td></tr>"}
          </tbody>
        </table>
      </section>

    </div>
  </body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home(
    question: str = "",
    tab: str = "chat",
    top_k: int = 3,
    retrieval_mode: str = "compare",
    debug: bool = False,
) -> HTMLResponse:
    active_tab = tab if tab in {"chat", "evaluation", "trace_review"} else "chat"
    top_k = max(1, min(top_k, 10))
    comparison = None
    result = None

    if question.strip():
        if retrieval_mode == "compare":
            comparison = service.compare_retrieval(question, top_k=top_k, debug=debug)
        else:
            result = service.answer(question, top_k=top_k, debug=debug, retrieval_mode=retrieval_mode)

    return HTMLResponse(
        render_page(
            question=question,
            active_tab=active_tab,
            top_k=top_k,
            result=result,
            comparison=comparison,
            retrieval_mode=retrieval_mode,
            debug=debug,
        )
    )


@app.post("/trace-review")
def trace_review(trace_id: str = Form("")) -> JSONResponse:
    try:
        service.review_trace(trace_id)
        return RedirectResponse(url="/?tab=trace_review&reviewed=" + trace_id, status_code=303)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

@app.get("/compare")
def compare_api(question: str, top_k: int = 3, debug: bool = False) -> JSONResponse:
    if not question.strip():
        raise HTTPException(status_code=400, detail="question parameter is required")
    return JSONResponse(service.compare_retrieval(question, top_k=top_k, debug=debug))


@app.post("/upload")
def upload(
    files: list[UploadFile] = File(...),
    chunk_strategy: str = Form("fixed_size"),
    chunk_size: int = Form(300),
    overlap: int = Form(100),
) -> RedirectResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    service.ingest_uploads(
        uploads=files,
        chunk_strategy=chunk_strategy,
        chunk_size=chunk_size,
        overlap=overlap,
    )
    return RedirectResponse(url="/", status_code=303)


@app.post("/clear")
def clear_all_data_web() -> RedirectResponse:
    service.clear_all_data()
    return RedirectResponse(url="/", status_code=303)


@app.delete("/clear")
def clear_all_data_api() -> JSONResponse:
    return JSONResponse(service.clear_all_data())


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
def query(
    question: str = Form(...),
    top_k: int = Form(4),
    debug: bool = Form(False),
    retrieval_mode: str = Form("hybrid"),
) -> JSONResponse:
    return JSONResponse(service.answer(question, top_k=top_k, debug=debug, retrieval_mode=retrieval_mode))


@app.post("/batch-query")
def batch_query(
    questions: list[str] = Body(...),
    top_k: int = 4,
    debug: bool = False,
    retrieval_mode: str = "hybrid",
) -> JSONResponse:
    return JSONResponse(service.answer_batch(questions, top_k=top_k, debug=debug, retrieval_mode=retrieval_mode))
