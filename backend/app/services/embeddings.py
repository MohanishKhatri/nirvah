"""PDF parsing, chunking, embedding and retrieval.

Embeddings are stored as JSON floats and compared in Python. At demo scale (a few hundred
chunks) that is instant, and it keeps the same code path on SQLite and Postgres. Swap
``search_relevant_chunks`` for a pgvector ``<=>`` query if the corpus ever grows.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Policy, PolicyChunk

logger = logging.getLogger(__name__)

EMBED_DIM = 768
EMBED_MODEL = "models/embedding-001"

SECTION_RE = re.compile(r"(?:§|Section\s+)(\d+(?:\.\d+)*)", re.IGNORECASE)


def _live() -> bool:
    return bool(settings.gemini_api_key) and not settings.use_llm_mock


# ------------------------------------------------------------------ pdf → text

def extract_text_from_pdf(file_path: str) -> list[dict]:
    """Returns [{'text': ..., 'page': n}] — one entry per non-empty page."""
    import pdfplumber

    pages: list[dict] = []
    with pdfplumber.open(file_path) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append({"text": text, "page": index})
    return pages


def _split_paragraphs(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Blank lines, then clause markers, then word windows — whichever the document offers.

    A PDF page often comes back as one run of lines with no blank lines at all, so falling
    through to the clause markers (and finally to fixed windows) is what keeps chunks useful.
    """
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]

    clause_split: list[str] = []
    for block in blocks:
        pieces = re.split(r"\n(?=(?:§|Section\s+)\d)", block)
        clause_split.extend(p.strip() for p in pieces if p.strip())

    sized: list[str] = []
    step = max(chunk_size - overlap, 1)
    for piece in clause_split:
        words = piece.split()
        if len(words) <= chunk_size:
            sized.append(piece)
            continue
        for start in range(0, len(words), step):
            window = words[start : start + chunk_size]
            if window:
                sized.append(" ".join(window))
            if start + chunk_size >= len(words):
                break
    return sized


def chunk_text(pages: Iterable[dict], chunk_size: int = 70, overlap: int = 20) -> list[dict]:
    """Paragraph-aware overlapping chunks.

    Policy documents state one rule per paragraph, so chunks are grown paragraph by paragraph
    up to ``chunk_size`` words. A chunk carries the section number of the first clause in it,
    which is what ends up in the citation.
    """
    chunks: list[dict] = []

    for page in pages:
        paragraphs = _split_paragraphs(page["text"], chunk_size, overlap)
        if not paragraphs:
            continue

        buffer: list[str] = []
        buffer_words = 0

        def flush(buf: list[str]) -> None:
            if not buf:
                return
            text = "\n\n".join(buf)
            match = SECTION_RE.search(text)
            chunks.append(
                {
                    "text": text,
                    "page": page["page"],
                    "source_section": f"§{match.group(1)}" if match else None,
                }
            )

        for paragraph in paragraphs:
            words = len(paragraph.split())
            if buffer and buffer_words + words > chunk_size:
                flush(buffer)
                # carry the tail paragraph forward so a rule spanning the boundary is not lost
                buffer = buffer[-1:] if overlap else []
                buffer_words = len(buffer[0].split()) if buffer else 0
            buffer.append(paragraph)
            buffer_words += words

        flush(buffer)

    return chunks


# ------------------------------------------------------------------ embedding

def _local_embed(text: str) -> list[float]:
    """Hashed bag-of-words vector — a lexical stand-in used when no Gemini key is configured."""
    vec = [0.0] * EMBED_DIM
    for token in re.findall(r"[a-z0-9₹.]+", text.lower()):
        if len(token) < 2:
            continue
        digest = hashlib.md5(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % EMBED_DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[index] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _gemini_embed(text: str, task_type: str) -> list[float]:
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    result = genai.embed_content(model=EMBED_MODEL, content=text, task_type=task_type)
    return list(result["embedding"])


def embed_text(text: str) -> list[float]:
    """Embedding for a stored document chunk."""
    if not _live():
        return _local_embed(text)
    try:
        return _gemini_embed(text, "retrieval_document")
    except Exception:
        logger.exception("embed_text failed; using local embedding")
        return _local_embed(text)


def embed_query(text: str) -> list[float]:
    """Embedding for a search query — Gemini optimises these differently from documents."""
    if not _live():
        return _local_embed(text)
    try:
        return _gemini_embed(text, "retrieval_query")
    except Exception:
        logger.exception("embed_query failed; using local embedding")
        return _local_embed(text)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ------------------------------------------------------------------- pipeline

async def ingest_policy(db: AsyncSession, policy_id: int, file_path: str) -> int:
    """extract → chunk → embed → store. Returns the number of chunks written."""
    await db.execute(delete(PolicyChunk).where(PolicyChunk.policy_id == policy_id))

    pages = extract_text_from_pdf(file_path)
    chunks = chunk_text(pages)

    written = 0
    for chunk in chunks:
        try:
            embedding = embed_text(chunk["text"])
        except Exception:
            logger.exception("skipping chunk that could not be embedded")
            continue
        db.add(
            PolicyChunk(
                policy_id=policy_id,
                chunk_text=chunk["text"],
                embedding=embedding,
                page_number=chunk["page"],
                source_section=chunk["source_section"],
            )
        )
        written += 1

    await db.commit()
    return written


async def ingest_text(
    db: AsyncSession, policy_id: int, text: str, page: int = 1
) -> int:
    """Same pipeline for plain text — used by the seed script so it needs no PDFs."""
    await db.execute(delete(PolicyChunk).where(PolicyChunk.policy_id == policy_id))
    chunks = chunk_text([{"text": text, "page": page}])
    for chunk in chunks:
        db.add(
            PolicyChunk(
                policy_id=policy_id,
                chunk_text=chunk["text"],
                embedding=embed_text(chunk["text"]),
                page_number=chunk["page"],
                source_section=chunk["source_section"],
            )
        )
    await db.commit()
    return len(chunks)


async def search_relevant_chunks(
    db: AsyncSession, query_text: str, top_k: int = 8
) -> list[dict]:
    query_vec = embed_query(query_text)

    rows = (
        await db.execute(
            select(PolicyChunk, Policy.name)
            .join(Policy, Policy.id == PolicyChunk.policy_id)
            .where(Policy.is_active.is_(True))
        )
    ).all()

    scored = []
    for chunk, policy_name in rows:
        scored.append(
            {
                "chunk_text": chunk.chunk_text,
                "policy_name": policy_name,
                "source_section": chunk.source_section,
                "page_number": chunk.page_number,
                "similarity": cosine_similarity(query_vec, chunk.embedding or []),
            }
        )

    scored.sort(key=lambda c: c["similarity"], reverse=True)
    return scored[:top_k]
