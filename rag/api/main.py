"""Entry point: FastAPI app, lifespan boot, router wiring, static mount."""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api import db
from api.articles import article_row_id, ensure_articles_collection
from api.core import ARTICLES_COLLECTION, INBOX_DIR, PROCESSED_DIR, ensure_models, log, qdrant
from api.pdfs import ensure_pdfs_collection, ingest_existing_files, start_watcher
from api.routes_admin import router as admin_router
from api.routes_articles import router as articles_router
from api.routes_news import router as news_router
from api.routes_pdfs import router as pdfs_router


def backfill_news_from_qdrant() -> None:
    """One-shot at boot: ensure every unique URL in Qdrant has a row in Postgres."""
    seen: set[str] = set()
    offset = None
    backfilled = 0
    try:
        while True:
            res, offset = qdrant.scroll(
                collection_name=ARTICLES_COLLECTION,
                limit=256, with_payload=True, with_vectors=False, offset=offset,
            )
            for p in res:
                url = p.payload.get("url")
                if not url or url in seen:
                    continue
                seen.add(url)
                if p.payload.get("chunk_index", 0) != 0:
                    continue  # only backfill from the first chunk's payload
                try:
                    db.upsert_article({
                        "id": article_row_id(url),
                        "url": url,
                        "title": p.payload.get("title"),
                        "source": p.payload.get("source") or "?",
                        "author": p.payload.get("author"),
                        "published_at": p.payload.get("published_at"),
                        "ingested_at": p.payload.get("ingested_at"),
                        "extracted_at": p.payload.get("extracted_at"),
                        "content_hash": p.payload.get("content_hash"),
                        "word_count": p.payload.get("word_count"),
                        "reading_time_minutes": p.payload.get("reading_time_minutes"),
                        "language": p.payload.get("language"),
                        "extraction_method": p.payload.get("extraction_method"),
                        "summary": p.payload.get("summary"),
                        "rss_categories": None,
                        "n_chunks": p.payload.get("n_chunks", 1),
                    })
                    backfilled += 1
                except Exception as e:
                    log.warning(f"Backfill skipped {url}: {e}")
            if offset is None:
                break
        if backfilled:
            log.info(f"Backfilled {backfilled} articles into Postgres from Qdrant")
    except Exception as e:
        log.warning(f"Backfill aborted: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    def setup():
        log.info("Initialisation de la stack RAG...")
        ensure_models()
        ensure_pdfs_collection()
        ensure_articles_collection()
        try:
            db.init_db()
            backfill_news_from_qdrant()
        except Exception as e:
            log.error(f"Postgres unavailable, news endpoints will fail until it recovers: {e}")
        ingest_existing_files()
        start_watcher()
        log.info("Stack RAG prête")

    threading.Thread(target=setup, daemon=True).start()
    yield


app = FastAPI(title="RAG Local", lifespan=lifespan)

app.include_router(admin_router)
app.include_router(pdfs_router)
app.include_router(articles_router)
app.include_router(news_router)

STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
