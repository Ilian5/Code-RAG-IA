"""PDF pipeline: PDF → markdown → smart_chunk → embeddings → Qdrant. Watcher inotify."""

from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path

import pymupdf4llm
from qdrant_client.http import models as qmodels
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .chunking import smart_chunk
from .core import (
    INBOX_DIR,
    PDFS_COLLECTION,
    PROCESSED_DIR,
    embed,
    ensure_collection,
    log,
    now_iso,
    qdrant,
)


WATCHER_RUNNING = {"value": False}


def ensure_pdfs_collection() -> None:
    ensure_collection(
        PDFS_COLLECTION,
        indexes=[("source", qmodels.PayloadSchemaType.KEYWORD)],
    )


def pdf_to_markdown(path: Path) -> str:
    return pymupdf4llm.to_markdown(str(path))


def delete_chunks_for_source(source_name: str) -> int:
    try:
        cnt = qdrant.count(
            collection_name=PDFS_COLLECTION,
            count_filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="source", match=qmodels.MatchValue(value=source_name))]
            ),
        ).count
    except Exception:
        cnt = 0
    try:
        qdrant.delete(
            collection_name=PDFS_COLLECTION,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[qmodels.FieldCondition(key="source", match=qmodels.MatchValue(value=source_name))]
                )
            ),
        )
    except Exception as e:
        log.exception(f"Erreur suppression chunks pour {source_name}: {e}")
        return 0
    return cnt


def ingest_pdf(path: Path, replace_existing: bool = True) -> dict:
    log.info(f"Ingestion de {path.name}")
    try:
        if replace_existing:
            removed = delete_chunks_for_source(path.name)
            if removed:
                log.info(f"  {removed} anciens chunks supprimés")

        md = pdf_to_markdown(path)
        if not md.strip():
            log.warning(f"  PDF vide ou non extractible : {path.name}")
            return {"status": "empty", "file": path.name}

        chunks = smart_chunk(md)
        if not chunks:
            return {"status": "empty", "file": path.name}

        log.info(f"  {len(chunks)} chunks structurés générés")

        points = []
        for i, c in enumerate(chunks):
            vector = embed(c["text"])
            points.append(qmodels.PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "source": path.name,
                    "chunk_index": i,
                    "heading": c["heading"],
                    "level": c["level"],
                    "text": c["text"],
                    "ingested_at": now_iso(),
                },
            ))
        qdrant.upsert(collection_name=PDFS_COLLECTION, points=points)

        if path.parent == INBOX_DIR:
            dest = PROCESSED_DIR / path.name
            if dest.exists():
                dest.unlink()
            shutil.move(str(path), str(dest))

        log.info(f"  ingéré {len(chunks)} chunks depuis {path.name}")
        return {"status": "ok", "file": path.name, "chunks": len(chunks)}
    except Exception as e:
        log.exception(f"Erreur ingestion {path.name}: {e}")
        return {"status": "error", "file": path.name, "error": str(e)}


def ingest_existing_files() -> None:
    pdfs = list(INBOX_DIR.glob("*.pdf")) + list(INBOX_DIR.glob("*.PDF"))
    if pdfs:
        log.info(f"{len(pdfs)} PDFs en attente dans inbox/")
        for p in pdfs:
            ingest_pdf(p)


class _PdfHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() != ".pdf":
            return
        # Wait for the writer to finish flushing.
        time.sleep(2)
        if path.exists():
            ingest_pdf(path)


def start_watcher() -> None:
    observer = Observer()
    observer.schedule(_PdfHandler(), str(INBOX_DIR), recursive=False)
    observer.start()
    WATCHER_RUNNING["value"] = True
    log.info(f"Watcher actif sur {INBOX_DIR}")
