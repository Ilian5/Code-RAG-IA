"""Article pipeline: trafilatura → smart_chunk → embeddings → Qdrant.

Idempotent (uuid5 from URL+chunk_index). Cross-URL deduplication via sha256(markdown).
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Optional

import httpx
import trafilatura
from pydantic import BaseModel, Field
from qdrant_client.http import models as qmodels

from .chunking import smart_chunk
from .core import ARTICLES_COLLECTION, embed, ensure_collection, log, now_iso, qdrant
from . import db


_URL_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
WORDS_PER_MINUTE = 200
MIN_EXTRACTED_CHARS = 200
USER_AGENT = "Mozilla/5.0 (compatible; RAG-extractor/1.0)"


# ============================================================
# Pydantic models
# ============================================================

class ArticleIngestReq(BaseModel):
    url: str
    title: Optional[str] = None
    # Preferred field name. Legacy n8n payloads may send "content" instead.
    content_html: Optional[str] = None
    content: Optional[str] = None
    source: str
    author: Optional[str] = None
    published_at: Optional[str] = None
    summary_rss: Optional[str] = Field(default=None, alias="summary")

    model_config = {"populate_by_name": True, "extra": "ignore"}

    def html(self) -> str:
        return self.content_html or self.content or ""


class ArticlesQueryReq(BaseModel):
    question: str
    top_k: Optional[int] = None
    source: Optional[str] = None
    since_days: Optional[int] = None


# ============================================================
# Collection bootstrap
# ============================================================

def ensure_articles_collection() -> None:
    ensure_collection(
        ARTICLES_COLLECTION,
        indexes=[
            ("source", qmodels.PayloadSchemaType.KEYWORD),
            ("url", qmodels.PayloadSchemaType.KEYWORD),
            ("content_hash", qmodels.PayloadSchemaType.KEYWORD),
            ("language", qmodels.PayloadSchemaType.KEYWORD),
            ("published_at", qmodels.PayloadSchemaType.DATETIME),
        ],
    )


# ============================================================
# Extraction
# ============================================================

def extract_article_markdown(html: str) -> tuple[str, dict]:
    """Returns (markdown, metadata).

    metadata keys: language, author, title, date, sitename (any may be None).
    """
    if not html:
        return "", {}

    md = trafilatura.extract(
        html,
        output_format="markdown",
        include_links=False,
        include_images=False,
        include_comments=False,
        include_tables=True,
        deduplicate=True,
        favor_precision=True,
    ) or ""

    meta_obj = trafilatura.extract_metadata(html)
    meta = {
        "language": getattr(meta_obj, "language", None) if meta_obj else None,
        "author": getattr(meta_obj, "author", None) if meta_obj else None,
        "title": getattr(meta_obj, "title", None) if meta_obj else None,
        "date": getattr(meta_obj, "date", None) if meta_obj else None,
        "sitename": getattr(meta_obj, "sitename", None) if meta_obj else None,
    }
    return md.strip(), meta


def fetch_url(url: str, timeout: float = 15.0) -> str:
    with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


def article_id(url: str, chunk_index: int) -> str:
    return str(uuid.uuid5(_URL_NAMESPACE, f"{url}#{chunk_index}"))


def article_row_id(url: str) -> str:
    """UUID for the row in the news.articles table — same namespace, no chunk suffix."""
    return str(uuid.uuid5(_URL_NAMESPACE, url))


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def derive_metrics(markdown: str) -> tuple[int, int]:
    """Returns (word_count, reading_time_minutes)."""
    word_count = len(markdown.split())
    reading_time = max(1, round(word_count / WORDS_PER_MINUTE))
    return word_count, reading_time


# ============================================================
# Ingestion
# ============================================================

def _delete_url(url: str) -> None:
    try:
        qdrant.delete(
            collection_name=ARTICLES_COLLECTION,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[qmodels.FieldCondition(key="url", match=qmodels.MatchValue(value=url))]
                )
            ),
        )
    except Exception:
        pass


def _find_canonical_url(hash_value: str, exclude_url: str) -> Optional[str]:
    """If another URL already has this content_hash, return it."""
    try:
        res, _ = qdrant.scroll(
            collection_name=ARTICLES_COLLECTION,
            scroll_filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="content_hash", match=qmodels.MatchValue(value=hash_value))]
            ),
            limit=8,
            with_payload=["url"],
            with_vectors=False,
        )
    except Exception:
        return None
    for p in res:
        u = p.payload.get("url")
        if u and u != exclude_url:
            return u
    return None


def ingest_article(req: ArticleIngestReq) -> dict:
    """Idempotent: same URL → same Qdrant IDs (upsert replaces).
    Cross-URL dedup: same content_hash under another URL → status=duplicate, no insert.
    """
    try:
        ensure_articles_collection()
        html = req.html()

        # 1. Extraction
        md, meta = extract_article_markdown(html)

        # 2. Validation length, fallback on RSS summary
        extraction_method = "trafilatura"
        if len(md) < MIN_EXTRACTED_CHARS:
            fallback = (req.summary_rss or "").strip()
            if fallback:
                md = fallback
                extraction_method = "rss_summary"
            else:
                return {"status": "empty", "url": req.url, "reason": "extracted markdown too short and no RSS summary"}

        if not md:
            return {"status": "empty", "url": req.url}

        # 3. Content hash
        h = content_hash(md)

        # 4. Cross-URL deduplication
        canonical = _find_canonical_url(h, req.url)
        if canonical:
            log.info(f"Article dupliqué (même hash que {canonical}): {req.url}")
            return {"status": "duplicate", "url": req.url, "canonical_url": canonical}

        # 5. Derived metrics
        word_count, reading_time = derive_metrics(md)
        title = req.title or meta.get("title") or "(sans titre)"

        # 6. Idempotence: drop existing chunks for this exact URL before re-insert
        _delete_url(req.url)

        # 7. Structural chunking — same as PDFs
        chunks = smart_chunk(f"# {title}\n\n{md}")
        if not chunks:
            return {"status": "empty", "url": req.url}

        # 8. Embed + upsert with deterministic IDs
        common_payload = {
            "url": req.url,
            "title": title,
            "source": req.source,
            "author": req.author or meta.get("author"),
            "published_at": req.published_at or meta.get("date"),
            "ingested_at": now_iso(),
            "extracted_at": now_iso(),
            "content_hash": h,
            "word_count": word_count,
            "reading_time_minutes": reading_time,
            "language": meta.get("language"),
            "extraction_method": extraction_method,
            "summary": req.summary_rss,
        }

        points = []
        for i, c in enumerate(chunks):
            vector = embed(c["text"])
            points.append(qmodels.PointStruct(
                id=article_id(req.url, i),
                vector=vector,
                payload={
                    **common_payload,
                    "chunk_index": i,
                    "n_chunks": len(chunks),
                    "text": c["text"],
                    "heading": c["heading"],
                },
            ))

        qdrant.upsert(collection_name=ARTICLES_COLLECTION, points=points)

        # Mirror metadata into Postgres for the consumer aggregator (news.leoharlay.dev).
        # If Postgres is unavailable, log and continue — RAG is the priority.
        try:
            db.upsert_article({
                "id": article_row_id(req.url),
                "url": req.url,
                "title": title,
                "source": req.source,
                "author": common_payload["author"],
                "published_at": common_payload["published_at"],
                "ingested_at": common_payload["ingested_at"],
                "extracted_at": common_payload["extracted_at"],
                "content_hash": h,
                "word_count": word_count,
                "reading_time_minutes": reading_time,
                "language": meta.get("language"),
                "extraction_method": extraction_method,
                "summary": req.summary_rss,
                "rss_categories": None,
                "n_chunks": len(chunks),
            })
        except Exception as e:
            log.warning(f"Postgres upsert failed for {req.url}: {e}")

        log.info(f"Article ingéré: {title[:60]} ({len(chunks)} chunks, {word_count} mots, {extraction_method})")
        return {
            "status": "ok",
            "url": req.url,
            "chunks": len(chunks),
            "word_count": word_count,
            "reading_time_minutes": reading_time,
            "extraction_method": extraction_method,
            "language": meta.get("language"),
        }

    except Exception as e:
        log.exception(f"Erreur ingestion article {req.url}: {e}")
        return {"status": "error", "url": req.url, "error": str(e)}
