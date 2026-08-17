from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


WORD_RE = re.compile(r"\S+")


def ensure_dirs(paths: Iterable[Path]) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def chunk_text_fixed(text: str, chunk_size: int, overlap: int) -> list[str]:
    words = WORD_RE.findall(clean_text(text))
    if not words:
        return []

    if chunk_size <= 0:
        chunk_size = 1
    if overlap < 0:
        overlap = 0
    if overlap >= chunk_size:
        overlap = max(0, chunk_size - 1)

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(len(words), start + chunk_size)
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = max(end - overlap, start + 1)
    return chunks


def chunk_text_sentence(text: str, max_words: int = 300, overlap_sentences: int = 1) -> list[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return []

    raw_sentences = [s.strip() for s in SENTENCE_RE.split(cleaned) if s.strip()]
    if not raw_sentences:
        return []

    if max_words <= 0:
        max_words = 1
    if overlap_sentences < 0:
        overlap_sentences = 0

    chunks: list[str] = []
    current_sentences: list[str] = []
    current_word_count = 0

    for sentence in raw_sentences:
        s_words = len(WORD_RE.findall(sentence))
        if current_sentences and (current_word_count + s_words > max_words):
            chunks.append(" ".join(current_sentences))
            if overlap_sentences > 0 and len(current_sentences) >= overlap_sentences:
                current_sentences = current_sentences[-overlap_sentences:]
                current_word_count = sum(len(WORD_RE.findall(s)) for s in current_sentences)
            else:
                current_sentences = []
                current_word_count = 0

        current_sentences.append(sentence)
        current_word_count += s_words

    if current_sentences:
        chunks.append(" ".join(current_sentences))

    return chunks


def chunk_text_structure_aware(text: str, max_chunk_words: int = 400) -> list[str]:
    if not text or not text.strip():
        return []

    lines = text.splitlines()
    main_title = ""
    for line in lines:
        line_s = line.strip()
        if line_s.startswith("# "):
            main_title = line_s
            break

    sections: list[tuple[str, list[str]]] = []
    current_header = main_title
    current_lines: list[str] = []
    in_code_block = False

    for line in lines:
        line_s = line.strip()

        if line_s.startswith("```"):
            in_code_block = not in_code_block

        if (
            not in_code_block
            and (line_s.startswith("# ") or line_s.startswith("## ") or line_s.startswith("### "))
            and current_lines
        ):
            sec_body = "\n".join(current_lines).strip()
            if sec_body:
                sections.append((current_header, current_lines))
            current_header = line_s
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sec_body = "\n".join(current_lines).strip()
        if sec_body:
            sections.append((current_header, current_lines))

    chunks: list[str] = []
    for header, sec_line_list in sections:
        body = "\n".join(sec_line_list).strip()
        if not body:
            continue

        if main_title and not body.startswith(main_title):
            chunk_text_val = f"{main_title}\n\n{body}"
        else:
            chunk_text_val = body

        chunks.append(chunk_text_val)

    return chunks if chunks else [text]


def chunk_text(text: str, chunk_size: int, overlap: int, strategy: str = "fixed_size") -> list[str]:
    if strategy == "structure_aware":
        return chunk_text_structure_aware(text, max_chunk_words=chunk_size)
    if strategy == "sentence":
        overlap_sentences = 1 if overlap > 0 else 0
        return chunk_text_sentence(text, max_words=chunk_size, overlap_sentences=overlap_sentences)
    return chunk_text_fixed(text, chunk_size=chunk_size, overlap=overlap)



def snippet(text: str, limit: int = 220) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def slugify_filename(name: str) -> str:
    stem = Path(name).stem.lower()
    stem = re.sub(r"[^a-z0-9]+", "-", stem)
    return stem.strip("-") or "document"


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        dot += a * b
        left_norm += a * a
        right_norm += b * b

    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return dot / ((left_norm ** 0.5) * (right_norm ** 0.5))

