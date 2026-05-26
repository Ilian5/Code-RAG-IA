"""Admin routes: overview stats, config, logs, root redirect, dashboard."""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse

from .core import (
    ARTICLES_COLLECTION,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBED_DIM,
    EMBED_MODEL,
    INBOX_DIR,
    LLM_MODEL,
    LOG_BUFFER,
    OLLAMA_URL,
    PDFS_COLLECTION,
    PROCESSED_DIR,
    QDRANT_URL,
    TOP_K,
    qdrant,
)
from .pdfs import WATCHER_RUNNING


router = APIRouter()


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@router.get("/")
def root_redirect() -> HTMLResponse:
    return HTMLResponse('<meta http-equiv="refresh" content="0;url=/admin">Redirecting…')


@router.get("/admin", response_class=HTMLResponse)
def admin_page() -> HTMLResponse:
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return HTMLResponse("<h1>Dashboard non trouvé</h1>", status_code=404)


@router.get("/health")
@router.get("/api/health")
def health() -> dict:
    try:
        ollama_ok = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5).status_code == 200
    except Exception:
        ollama_ok = False
    try:
        qdrant_ok = qdrant.get_collections() is not None
    except Exception:
        qdrant_ok = False
    return {"ollama": ollama_ok, "qdrant": qdrant_ok}


@router.get("/api/overview")
def overview() -> dict:
    try:
        info = qdrant.get_collection(PDFS_COLLECTION)
        chunks_total = info.points_count or 0
    except Exception:
        chunks_total = 0

    unique_docs = 0
    try:
        sources: set[str] = set()
        offset = None
        while True:
            res, offset = qdrant.scroll(
                collection_name=PDFS_COLLECTION,
                limit=512,
                with_payload=["source"],
                with_vectors=False,
                offset=offset,
            )
            for p in res:
                src = p.payload.get("source")
                if src:
                    sources.add(src)
            if offset is None:
                break
        unique_docs = len(sources)
    except Exception:
        pass

    inbox_count = len(list(INBOX_DIR.glob("*.pdf"))) + len(list(INBOX_DIR.glob("*.PDF")))
    processed_count = len(list(PROCESSED_DIR.glob("*.pdf"))) + len(list(PROCESSED_DIR.glob("*.PDF")))

    try:
        ollama_ok = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5).status_code == 200
    except Exception:
        ollama_ok = False
    try:
        qdrant_ok = qdrant.get_collections() is not None
    except Exception:
        qdrant_ok = False

    models = []
    try:
        with httpx.Client(timeout=10) as c:
            tags = c.get(f"{OLLAMA_URL}/api/tags").json()
            for m in tags.get("models", []):
                models.append({
                    "name": m.get("name"),
                    "size": m.get("size"),
                    "modified_at": m.get("modified_at"),
                })
    except Exception:
        pass

    try:
        articles_info = qdrant.get_collection(ARTICLES_COLLECTION)
        articles_chunks = articles_info.points_count or 0
    except Exception:
        articles_chunks = 0

    return {
        "chunks_total": chunks_total,
        "unique_docs": unique_docs,
        "inbox_count": inbox_count,
        "processed_count": processed_count,
        "ollama_ok": ollama_ok,
        "qdrant_ok": qdrant_ok,
        "watcher_ok": WATCHER_RUNNING["value"],
        "models": models,
        "articles_chunks": articles_chunks,
    }


@router.get("/api/config")
def config() -> dict:
    return {
        "LLM_MODEL": LLM_MODEL,
        "EMBED_MODEL": EMBED_MODEL,
        "CHUNK_SIZE": CHUNK_SIZE,
        "CHUNK_OVERLAP": CHUNK_OVERLAP,
        "TOP_K": TOP_K,
        "INBOX_DIR": str(INBOX_DIR),
        "PROCESSED_DIR": str(PROCESSED_DIR),
        "PDFS_COLLECTION": PDFS_COLLECTION,
        "ARTICLES_COLLECTION": ARTICLES_COLLECTION,
        "EMBED_DIM": EMBED_DIM,
        "OLLAMA_URL": OLLAMA_URL,
        "QDRANT_URL": QDRANT_URL,
    }


@router.get("/api/logs")
def logs(level: str = "", count: int = 100) -> dict:
    lines = list(LOG_BUFFER)
    if level:
        wanted = {
            "INFO": ("INFO", "WARNING", "ERROR"),
            "WARNING": ("WARNING", "ERROR"),
            "ERROR": ("ERROR",),
        }.get(level, ())
        if wanted:
            lines = [l for l in lines if any(f"[{w}]" in l for w in wanted)]
    lines = lines[-count:]
    return {"lines": lines, "count": len(lines)}
