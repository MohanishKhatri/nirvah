"""PDF parsing, chunking, embedding and retrieval.

Embeddings are stored as JSON floats and compared in Python. At demo scale (a few hundred
chunks) that is instant, and it keeps the same code path on SQLite and Postgres. Swap
``search_relevant_chunks`` for a pgvector ``<=>`` query if the corpus ever grows.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Policy, PolicyChunk

logger = logging.getLogger(__name__)

#: all-MiniLM-L6-v2's native output size — retrieval quality is solid for policy-length text,
#: it's ~80MB, and it runs fast on CPU with no GPU needed at this corpus size.
EMBED_DIM = 384
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

SECTION_RE = re.compile(r"(?:§|Section\s+)(\d+(?:\.\d+)*)", re.IGNORECASE)


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

_st_model = None


def _get_model():
    """Lazy singleton — loading the model is the expensive part, so pay for it once."""
    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer

        _st_model = SentenceTransformer(EMBED_MODEL)
    return _st_model


def embed_text(text: str) -> list[float]:
    """Embedding for a stored document chunk."""
    return _get_model().encode(text, normalize_embeddings=True).tolist()


def embed_query(text: str) -> list[float]:
    """Embedding for a search query.

    Unlike Gemini's embedding API, MiniLM has no separate query/document task type — it's a
    symmetric similarity model, so this is the same call as ``embed_text``. Kept as its own
    function so callers don't need to care which kind of text they're embedding.
    """
    return embed_text(text)


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
    db: AsyncSession, query_text: str, top_k: int = 12
) -> list[dict]:
    """top_k=12, not 8: a genuinely relevant chunk (e.g. Finance Policy's expenditure threshold)
    has been observed ranking 9th on a real query — a small local model's similarity scores
    cluster tightly, so a tight cutoff drops real matches by a narrow margin. 12 chunks is still
    cheap for a flash-lite prompt and gives that margin some room."""
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
