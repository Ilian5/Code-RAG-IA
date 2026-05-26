"""PDF + generic query routes (the legacy PDF endpoints, untouched in shape)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from qdrant_client.http import models as qmodels

from .core import INBOX_DIR, PDFS_COLLECTION, PROCESSED_DIR, TOP_K, embed, generate, qdrant
from .pdfs import (
    delete_chunks_for_source,
    ensure_pdfs_collection,
    ingest_pdf,
    pdf_to_markdown,
)


router = APIRouter()


class QueryReq(BaseModel):
    question: str
    top_k: int | None = None


@router.post("/query")
@router.post("/api/query")
def query(req: QueryReq) -> dict:
    if not req.question.strip():
        raise HTTPException(400, "Question vide")
    k = req.top_k or TOP_K
    qvec = embed(req.question)

    results = qdrant.search(
        collection_name=PDFS_COLLECTION,
        query_vector=qvec,
        limit=k,
    )

    if not results:
        return {"answer": "Aucun document indexé ne semble contenir d'information pertinente.", "sources": []}

    context_parts = []
    sources = []
    for i, r in enumerate(results, 1):
        text = r.payload.get("text", "")
        source = r.payload.get("source", "?")
        heading = r.payload.get("heading", "")
        context_parts.append(f"[Extrait {i} — source: {source}]\n{text}")
        sources.append({
            "source": source,
            "score": r.score,
            "chunk_index": r.payload.get("chunk_index", -1),
            "heading": heading,
        })

    context = "\n\n".join(context_parts)
    prompt = (
        "Tu es un assistant qui répond UNIQUEMENT en t'appuyant sur les extraits ci-dessous.\n"
        "Si l'information n'y figure pas, dis-le clairement.\n"
        "Cite les sources entre crochets quand tu utilises une information précise.\n\n"
        f"=== EXTRAITS ===\n{context}\n\n"
        f"=== QUESTION ===\n{req.question}\n\n"
        "=== RÉPONSE ==="
    )
    answer = generate(prompt)
    return {"answer": answer.strip(), "sources": sources}


@router.get("/api/files")
def files() -> dict:
    chunks_by_source: dict[str, int] = {}
    try:
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
                s = p.payload.get("source")
                if s:
                    chunks_by_source[s] = chunks_by_source.get(s, 0) + 1
            if offset is None:
                break
    except Exception:
        pass

    def info(path, with_chunks):
        try:
            stat = path.stat()
            return {
                "name": path.name,
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "chunks": chunks_by_source.get(path.name) if with_chunks else None,
            }
        except Exception:
            return {"name": path.name, "size": None, "mtime": None, "chunks": None}

    inbox = sorted(list(INBOX_DIR.glob("*.pdf")) + list(INBOX_DIR.glob("*.PDF")), key=lambda p: p.name)
    processed = sorted(list(PROCESSED_DIR.glob("*.pdf")) + list(PROCESSED_DIR.glob("*.PDF")), key=lambda p: p.name)
    return {
        "inbox": [info(p, False) for p in inbox],
        "processed": [info(p, True) for p in processed],
    }


@router.get("/api/preview-md")
def preview_md(filename: str = Query(...)) -> dict:
    candidates = [PROCESSED_DIR / filename, INBOX_DIR / filename]
    path = next((p for p in candidates if p.exists()), None)
    if not path:
        raise HTTPException(404, f"Fichier introuvable: {filename}")
    try:
        md = pdf_to_markdown(path)
        return {"filename": filename, "markdown": md, "length": len(md)}
    except Exception as e:
        raise HTTPException(500, f"Erreur extraction: {e}")


@router.get("/api/file-chunks")
def file_chunks(filename: str = Query(...), limit: int = Query(200, le=1000)) -> dict:
    chunks: list[dict] = []
    try:
        offset = None
        while len(chunks) < limit:
            res, offset = qdrant.scroll(
                collection_name=PDFS_COLLECTION,
                scroll_filter=qmodels.Filter(
                    must=[qmodels.FieldCondition(key="source", match=qmodels.MatchValue(value=filename))]
                ),
                limit=min(256, limit - len(chunks)),
                with_payload=True,
                with_vectors=False,
                offset=offset,
            )
            for p in res:
                chunks.append({
                    "id": p.id,
                    "source": p.payload.get("source"),
                    "chunk_index": p.payload.get("chunk_index"),
                    "heading": p.payload.get("heading", ""),
                    "text": p.payload.get("text", ""),
                })
            if offset is None:
                break
        chunks.sort(key=lambda c: c["chunk_index"] if c["chunk_index"] is not None else 0)
        return {"filename": filename, "chunks": chunks, "count": len(chunks)}
    except Exception as e:
        raise HTTPException(500, f"Erreur: {e}")


@router.get("/api/all-chunks")
def all_chunks(limit: int = Query(50, le=500)) -> dict:
    chunks: list[dict] = []
    try:
        offset = None
        while len(chunks) < limit:
            res, offset = qdrant.scroll(
                collection_name=PDFS_COLLECTION,
                limit=min(256, limit - len(chunks)),
                with_payload=True,
                with_vectors=False,
                offset=offset,
            )
            for p in res:
                chunks.append({
                    "id": p.id,
                    "source": p.payload.get("source"),
                    "chunk_index": p.payload.get("chunk_index"),
                    "heading": p.payload.get("heading", ""),
                    "text": p.payload.get("text", ""),
                })
            if offset is None:
                break
        return {"chunks": chunks, "count": len(chunks)}
    except Exception as e:
        raise HTTPException(500, f"Erreur: {e}")


@router.delete("/api/file")
def delete_file(filename: str = Query(...)) -> dict:
    removed = delete_chunks_for_source(filename)
    deleted_files = []
    for d in (PROCESSED_DIR, INBOX_DIR):
        p = d / filename
        if p.exists():
            try:
                p.unlink()
                deleted_files.append(str(p))
            except Exception:
                pass
    return {"filename": filename, "chunks_removed": removed, "files_deleted": deleted_files}


@router.post("/api/reingest")
def reingest(filename: str = Query(...)) -> dict:
    path = PROCESSED_DIR / filename
    if not path.exists():
        path = INBOX_DIR / filename
    if not path.exists():
        raise HTTPException(404, f"Fichier introuvable: {filename}")
    return ingest_pdf(path, replace_existing=True)


@router.post("/api/ingest-file")
def ingest_file(filename: str = Query(...)) -> dict:
    path = INBOX_DIR / filename
    if not path.exists():
        raise HTTPException(404, f"Fichier introuvable dans inbox: {filename}")
    return ingest_pdf(path, replace_existing=True)


@router.post("/api/reingest-all")
def reingest_all() -> dict:
    files = list(INBOX_DIR.glob("*.pdf")) + list(INBOX_DIR.glob("*.PDF"))
    files += list(PROCESSED_DIR.glob("*.pdf")) + list(PROCESSED_DIR.glob("*.PDF"))
    results = [ingest_pdf(f, replace_existing=True) for f in files]
    return {"processed": len(results), "results": results}


@router.delete("/api/clear")
@router.delete("/clear")
def clear() -> dict:
    qdrant.delete_collection(PDFS_COLLECTION)
    ensure_pdfs_collection()
    return {"status": "cleared"}


@router.post("/upload")
@router.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Seuls les PDFs sont supportés")
    dest = INBOX_DIR / file.filename
    with dest.open("wb") as f:
        f.write(await file.read())
    return ingest_pdf(dest, replace_existing=True)


@router.get("/api/stats")
@router.get("/stats")
def stats() -> dict:
    try:
        info = qdrant.get_collection(PDFS_COLLECTION)
        return {"documents_chunks": info.points_count, "collection": PDFS_COLLECTION}
    except Exception as e:
        return {"error": str(e)}
