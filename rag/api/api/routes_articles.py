"""Article routes: ingest, query, list, sources, stats, preview-extraction, duplicates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from qdrant_client.http import models as qmodels

from .articles import (
    ArticleIngestReq,
    ArticlesQueryReq,
    derive_metrics,
    ensure_articles_collection,
    extract_article_markdown,
    fetch_url,
    ingest_article,
)
from .core import ARTICLES_COLLECTION, TOP_K, embed, generate, log, qdrant
from . import db


router = APIRouter()


@router.post("/api/articles/ingest")
def ingest(article: ArticleIngestReq) -> dict:
    return ingest_article(article)


@router.post("/api/articles/ingest-batch")
def ingest_batch(articles: list[ArticleIngestReq]) -> dict:
    results = [ingest_article(a) for a in articles]
    ok = sum(1 for r in results if r.get("status") == "ok")
    duplicates = sum(1 for r in results if r.get("status") == "duplicate")
    return {"received": len(articles), "ok": ok, "duplicates": duplicates, "results": results}


@router.post("/api/articles/retrieve")
def retrieve(req: ArticlesQueryReq) -> dict:
    """Vector search only — returns relevant chunks with payload, no LLM synthesis.

    For agentic use (n8n agent, MCP retrieve_articles tool) where the caller wants
    raw chunks and will synthesize the answer with its own LLM.
    """
    if not req.question.strip():
        raise HTTPException(400, "Question vide")
    ensure_articles_collection()
    k = req.top_k or TOP_K
    qvec = embed(req.question)

    must = []
    if req.source:
        must.append(qmodels.FieldCondition(key="source", match=qmodels.MatchValue(value=req.source)))
    if req.since_days:
        threshold = (datetime.now(timezone.utc) - timedelta(days=req.since_days)).isoformat()
        must.append(qmodels.FieldCondition(key="published_at", range=qmodels.DatetimeRange(gte=threshold)))
    qf = qmodels.Filter(must=must) if must else None

    try:
        results = qdrant.search(
            collection_name=ARTICLES_COLLECTION,
            query_vector=qvec, query_filter=qf, limit=k,
        )
    except Exception:
        results = qdrant.search(collection_name=ARTICLES_COLLECTION, query_vector=qvec, limit=k)

    chunks = []
    for r in results:
        p = r.payload
        chunks.append({
            "title": p.get("title"),
            "source": p.get("source"),
            "url": p.get("url"),
            "published_at": p.get("published_at"),
            "heading": p.get("heading"),
            "chunk_index": p.get("chunk_index"),
            "text": p.get("text"),
            "score": r.score,
        })
    return {"chunks": chunks, "count": len(chunks)}


@router.post("/api/articles/query")
def query(req: ArticlesQueryReq) -> dict:
    if not req.question.strip():
        raise HTTPException(400, "Question vide")
    ensure_articles_collection()
    k = req.top_k or TOP_K
    qvec = embed(req.question)

    must: list = []
    if req.source:
        must.append(qmodels.FieldCondition(key="source", match=qmodels.MatchValue(value=req.source)))
    if req.since_days:
        threshold = (datetime.now(timezone.utc) - timedelta(days=req.since_days)).isoformat()
        must.append(qmodels.FieldCondition(key="published_at", range=qmodels.DatetimeRange(gte=threshold)))
    qf = qmodels.Filter(must=must) if must else None

    try:
        results = qdrant.search(
            collection_name=ARTICLES_COLLECTION,
            query_vector=qvec,
            query_filter=qf,
            limit=k,
        )
    except Exception:
        # DatetimeRange not supported: fall back to client-side filter.
        results = qdrant.search(
            collection_name=ARTICLES_COLLECTION,
            query_vector=qvec,
            limit=k * 3 if must else k,
        )
        if must:
            def _ok(r):
                p = r.payload
                if req.source and p.get("source") != req.source:
                    return False
                if req.since_days:
                    pa = p.get("published_at")
                    if not pa:
                        return False
                    try:
                        if datetime.fromisoformat(pa.replace("Z", "+00:00")) < datetime.now(timezone.utc) - timedelta(days=req.since_days):
                            return False
                    except Exception:
                        return False
                return True
            results = [r for r in results if _ok(r)][:k]

    if not results:
        return {"answer": "Aucun article ne correspond à la question.", "sources": []}

    context_parts = []
    sources = []
    for i, r in enumerate(results, 1):
        p = r.payload
        title = p.get("title", "?")
        src = p.get("source", "?")
        url = p.get("url", "")
        text = p.get("text", "")
        pub = p.get("published_at", "")
        context_parts.append(f"[Article {i} — {src} — \"{title}\" — {pub}]\n{text}")
        sources.append({
            "title": title,
            "source": src,
            "url": url,
            "published_at": pub,
            "score": r.score,
            "chunk_index": p.get("chunk_index", 0),
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
    return {"answer": answer.strip(), "sources": sources}


def _scroll_articles_unique(qf=None, threshold: Optional[datetime] = None, hard_cap: int = 5000):
    """Yields one payload per unique URL (the first one encountered, typically chunk 0)."""
    seen: set[str] = set()
    offset = None
    fetched = 0
    while fetched < hard_cap:
        res, offset = qdrant.scroll(
            collection_name=ARTICLES_COLLECTION,
            scroll_filter=qf,
            limit=256,
            with_payload=True,
            with_vectors=False,
            offset=offset,
        )
        fetched += len(res)
        for p in res:
            url = p.payload.get("url")
            if not url or url in seen:
                continue
            if threshold:
                pa = p.payload.get("published_at")
                if not pa:
                    continue
                try:
                    if datetime.fromisoformat(pa.replace("Z", "+00:00")) < threshold:
                        continue
                except Exception:
                    continue
            seen.add(url)
            yield p.payload
        if offset is None:
            break


@router.get("/api/articles/list")
def list_articles(
    source: Optional[str] = None,
    since_days: Optional[int] = None,
    limit: int = 50,
) -> dict:
    ensure_articles_collection()
    must = []
    if source:
        must.append(qmodels.FieldCondition(key="source", match=qmodels.MatchValue(value=source)))
    qf = qmodels.Filter(must=must) if must else None
    threshold = datetime.now(timezone.utc) - timedelta(days=since_days) if since_days else None

    articles = []
    for payload in _scroll_articles_unique(qf=qf, threshold=threshold):
        articles.append({
            "url": payload.get("url"),
            "title": payload.get("title"),
            "source": payload.get("source"),
            "author": payload.get("author"),
            "published_at": payload.get("published_at"),
            "ingested_at": payload.get("ingested_at"),
            "extracted_at": payload.get("extracted_at"),
            "summary": payload.get("summary"),
            "n_chunks": payload.get("n_chunks", 1),
            "word_count": payload.get("word_count"),
            "reading_time_minutes": payload.get("reading_time_minutes"),
            "language": payload.get("language"),
            "content_hash": payload.get("content_hash"),
            "extraction_method": payload.get("extraction_method"),
        })
        if len(articles) >= limit:
            break

    articles.sort(key=lambda a: a.get("published_at") or "", reverse=True)
    return {"count": len(articles), "articles": articles}


@router.get("/api/articles/sources")
def sources() -> dict:
    ensure_articles_collection()
    counts: dict[str, int] = {}
    for payload in _scroll_articles_unique():
        src = payload.get("source") or "?"
        counts[src] = counts.get(src, 0) + 1
    sources_list = [{"source": k, "articles": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]
    return {"sources": sources_list, "total_articles": sum(counts.values())}


@router.get("/api/articles/stats")
def stats() -> dict:
    ensure_articles_collection()
    try:
        info = qdrant.get_collection(ARTICLES_COLLECTION)
        chunks_total = info.points_count or 0
    except Exception:
        chunks_total = 0

    counts: dict[str, int] = {}
    total_words = 0
    languages: dict[str, int] = {}
    for payload in _scroll_articles_unique():
        src = payload.get("source") or "?"
        counts[src] = counts.get(src, 0) + 1
        wc = payload.get("word_count") or 0
        total_words += wc
        lang = payload.get("language") or "unknown"
        languages[lang] = languages.get(lang, 0) + 1

    sources_list = [{"source": k, "articles": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]
    return {
        "chunks_total": chunks_total,
        "unique_articles": sum(counts.values()),
        "sources": sources_list,
        "total_words": total_words,
        "languages": languages,
    }


@router.get("/api/articles/preview-extraction")
def preview_extraction(url: str = Query(..., min_length=4)) -> dict:
    """Fetch + extract without storing. Debug tool."""
    try:
        html = fetch_url(url)
    except Exception as e:
        raise HTTPException(502, f"Fetch failed: {e}")

    md, meta = extract_article_markdown(html)
    word_count, reading_time = derive_metrics(md or "")
    return {
        "url": url,
        "status": "ok" if md else "empty",
        "length": len(md or ""),
        "word_count": word_count,
        "reading_time_minutes": reading_time,
        "language": meta.get("language"),
        "metadata": meta,
        "markdown": md,
    }


@router.get("/api/articles/by-url")
def get_by_url(url: str = Query(...)) -> dict:
    """Returns the full payload + reconstructed markdown for one article."""
    ensure_articles_collection()
    res, _ = qdrant.scroll(
        collection_name=ARTICLES_COLLECTION,
        scroll_filter=qmodels.Filter(
            must=[qmodels.FieldCondition(key="url", match=qmodels.MatchValue(value=url))]
        ),
        limit=512,
        with_payload=True,
        with_vectors=False,
    )
    if not res:
        raise HTTPException(404, "Article introuvable")
    chunks = sorted(res, key=lambda p: p.payload.get("chunk_index", 0))
    base = chunks[0].payload
    markdown = "\n\n".join(c.payload.get("text", "") for c in chunks)
    return {
        "url": base.get("url"),
        "title": base.get("title"),
        "source": base.get("source"),
        "author": base.get("author"),
        "published_at": base.get("published_at"),
        "ingested_at": base.get("ingested_at"),
        "extracted_at": base.get("extracted_at"),
        "language": base.get("language"),
        "word_count": base.get("word_count"),
        "reading_time_minutes": base.get("reading_time_minutes"),
        "content_hash": base.get("content_hash"),
        "extraction_method": base.get("extraction_method"),
        "n_chunks": len(chunks),
        "summary": base.get("summary"),
        "markdown": markdown,
    }


@router.get("/api/articles/duplicates")
def duplicates() -> dict:
    """Lists content_hash values shared across multiple URLs (audit)."""
    ensure_articles_collection()
    by_hash: dict[str, set[str]] = {}
    for payload in _scroll_articles_unique():
        h = payload.get("content_hash")
        url = payload.get("url")
        if not h or not url:
            continue
        by_hash.setdefault(h, set()).add(url)
    groups = [
        {"content_hash": h, "urls": sorted(urls)}
        for h, urls in by_hash.items()
        if len(urls) > 1
    ]
    return {"groups": groups, "count": len(groups)}


@router.delete("/api/articles/by-url")
def delete_by_url(url: str = Query(...)) -> dict:
    ensure_articles_collection()
    pg_deleted = 0
    try:
        pg_deleted = db.delete_by_url(url)
    except Exception as e:
        log.warning(f"Postgres delete_by_url failed: {e}")
    try:
        qdrant.delete(
            collection_name=ARTICLES_COLLECTION,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[qmodels.FieldCondition(key="url", match=qmodels.MatchValue(value=url))]
                )
            ),
        )
        return {"status": "deleted", "url": url, "pg_rows": pg_deleted}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.delete("/api/articles/by-source")
def delete_by_source(source: str = Query(...)) -> dict:
    ensure_articles_collection()
    pg_deleted = 0
    try:
        pg_deleted = db.delete_by_source(source)
    except Exception as e:
        log.warning(f"Postgres delete_by_source failed: {e}")
    try:
        qdrant.delete(
            collection_name=ARTICLES_COLLECTION,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[qmodels.FieldCondition(key="source", match=qmodels.MatchValue(value=source))]
                )
            ),
        )
        return {"status": "deleted", "source": source, "pg_rows": pg_deleted}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.delete("/api/articles/clear")
def clear() -> dict:
    pg_truncated = 0
    try:
        pg_truncated = db.truncate_all()
    except Exception as e:
        log.warning(f"Postgres truncate failed: {e}")
    try:
        qdrant.delete_collection(ARTICLES_COLLECTION)
        ensure_articles_collection()
        return {"status": "cleared", "pg_rows": pg_truncated}
    except Exception as e:
        log.exception("Erreur clear articles")
        raise HTTPException(500, str(e))
