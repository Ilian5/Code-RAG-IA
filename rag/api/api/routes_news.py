"""News consumer routes: listing, filters, read state, stats, chat-with-filters."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from qdrant_client.http import models as qmodels

from . import db
from .articles import article_row_id
from .core import ARTICLES_COLLECTION, TOP_K, embed, generate, log, qdrant


router = APIRouter()


# ============================================================
# Pydantic models
# ============================================================

class ToggleReq(BaseModel):
    value: bool


class MarkAllReadReq(BaseModel):
    source: Optional[str] = None


class NewsChatReq(BaseModel):
    question: str
    top_k: Optional[int] = None
    sources: Optional[list[str]] = None
    since_days: Optional[int] = None
    unread_only: bool = False


# ============================================================
# Helpers
# ============================================================

def _serialize(row: dict) -> dict:
    """Convert Postgres row to JSON-friendly dict (datetime → ISO)."""
    out = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


# ============================================================
# Listing & detail
# ============================================================

@router.get("/api/news/list")
def list_news(
    source: Optional[str] = None,
    since_days: Optional[int] = None,
    unread: bool = False,
    starred: bool = False,
    q: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    order: str = "published_at_desc",
) -> dict:
    rows, total = db.list_articles(
        source=source, since_days=since_days, unread=unread, starred=starred,
        q=q, limit=limit, offset=offset, order=order,
    )
    return {
        "count": len(rows),
        "total": total,
        "limit": limit,
        "offset": offset,
        "articles": [_serialize(r) for r in rows],
    }


@router.get("/api/news/sources")
def sources() -> dict:
    rows = db.sources_with_counts()
    return {"sources": [_serialize(r) for r in rows]}


@router.get("/api/news/stats")
def stats() -> dict:
    return db.global_stats()


@router.post("/api/news/mark-all-read")
def mark_all(req: MarkAllReadReq) -> dict:
    n = db.mark_all_read(source=req.source)
    return {"marked_read": n, "source": req.source}


# Parametric routes LAST so they don't shadow the named ones above.

@router.get("/api/news/{article_id}")
def get_news(article_id: str) -> dict:
    row = db.get_article(article_id)
    if not row:
        raise HTTPException(404, "Article not found")
    markdown = ""
    try:
        res, _ = qdrant.scroll(
            collection_name=ARTICLES_COLLECTION,
            scroll_filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="url", match=qmodels.MatchValue(value=row["url"]))]
            ),
            limit=512, with_payload=True, with_vectors=False,
        )
        chunks = sorted(res, key=lambda p: p.payload.get("chunk_index", 0))
        markdown = "\n\n".join(c.payload.get("text", "") for c in chunks)
    except Exception as e:
        log.warning(f"Markdown reconstruction failed: {e}")
    return {**_serialize(row), "markdown": markdown}


@router.patch("/api/news/{article_id}/read")
def set_read(article_id: str, req: ToggleReq) -> dict:
    row = db.set_read(article_id, req.value)
    if not row:
        raise HTTPException(404, "Article not found")
    return _serialize(row)


@router.patch("/api/news/{article_id}/star")
def set_starred(article_id: str, req: ToggleReq) -> dict:
    row = db.set_starred(article_id, req.value)
    if not row:
        raise HTTPException(404, "Article not found")
    return _serialize(row)


# ============================================================
# Chat with filters (wraps RAG /api/articles/query)
# ============================================================

@router.post("/api/news/chat")
def chat(req: NewsChatReq) -> dict:
    if not req.question.strip():
        raise HTTPException(400, "Question vide")
    k = req.top_k or TOP_K
    qvec = embed(req.question)

    must: list = []
    if req.sources:
        # Qdrant supports `match: any` via MatchAny in recent client versions; fall back to OR of search calls if needed.
        must.append(qmodels.FieldCondition(key="source", match=qmodels.MatchAny(any=req.sources)))
    if req.since_days:
        threshold = (datetime.now(timezone.utc) - timedelta(days=req.since_days)).isoformat()
        must.append(qmodels.FieldCondition(key="published_at", range=qmodels.DatetimeRange(gte=threshold)))

    qf = qmodels.Filter(must=must) if must else None

    try:
        results = qdrant.search(
            collection_name=ARTICLES_COLLECTION, query_vector=qvec,
            query_filter=qf, limit=k * (3 if req.unread_only else 1),
        )
    except Exception as e:
        log.warning(f"Qdrant search failed, fallback: {e}")
        results = qdrant.search(collection_name=ARTICLES_COLLECTION, query_vector=qvec, limit=k * 3)

    # If unread_only, filter against Postgres read state.
    if req.unread_only and results:
        unread_urls = set()
        for r in results:
            row = db.get_article_by_url(r.payload.get("url", ""))
            if row and row.get("read_at") is None:
                unread_urls.add(r.payload.get("url"))
        results = [r for r in results if r.payload.get("url") in unread_urls][:k]
    else:
        results = results[:k]

    if not results:
        return {"answer": "Aucun article ne correspond.", "sources": []}

    context_parts = []
    sources_out = []
    for i, r in enumerate(results, 1):
        p = r.payload
        title = p.get("title", "?")
        src = p.get("source", "?")
        url = p.get("url", "")
        text = p.get("text", "")
        pub = p.get("published_at", "")
        context_parts.append(f"[Article {i} — {src} — \"{title}\" — {pub}]\n{text}")
        # Compute the news.articles row ID so the frontend can link directly to /article/[id]
        sources_out.append({
            "id": article_row_id(url) if url else None,
            "title": title, "source": src, "url": url, "published_at": pub,
            "score": r.score, "chunk_index": p.get("chunk_index", 0),
        })

    context = "\n\n".join(context_parts)
    prompt = (
        "Tu es un assistant qui synthétise l'actualité technique pour un développeur.\n"
        "Réponds en t'appuyant UNIQUEMENT sur les articles ci-dessous.\n"
        "Cite les sources entre crochets sous la forme [titre — source].\n"
        "Si aucun article ne traite vraiment du sujet, dis-le clairement.\n"
        "Sois factuel, concis, sans extrapoler.\n\n"
        f"=== ARTICLES ===\n{context}\n\n"
        f"=== QUESTION ===\n{req.question}\n\n"
        "=== RÉPONSE ==="
    )
    answer = generate(prompt)
    return {"answer": answer.strip(), "sources": sources_out}
