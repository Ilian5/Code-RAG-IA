"""Shared services: configuration, Qdrant client, Ollama helpers, logging."""

from __future__ import annotations

import logging
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2:3b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))
TOP_K = int(os.getenv("TOP_K", "5"))
INBOX_DIR = Path(os.getenv("INBOX_DIR", "/data/inbox"))
PROCESSED_DIR = Path(os.getenv("PROCESSED_DIR", "/data/processed"))

PDFS_COLLECTION = "documents"
ARTICLES_COLLECTION = "articles"
EMBED_DIM = 768

LOG_BUFFER: deque[str] = deque(maxlen=2000)


class _BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            LOG_BUFFER.append(self.format(record))
        except Exception:
            pass


def _setup_logging() -> logging.Logger:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    buffer_h = _BufferHandler()
    buffer_h.setFormatter(fmt)
    root.handlers = [console, buffer_h]
    return logging.getLogger("rag")


log = _setup_logging()
qdrant = QdrantClient(url=QDRANT_URL)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_collection(name: str, indexes: list[tuple[str, qmodels.PayloadSchemaType]] | None = None) -> bool:
    """Idempotent: creates the collection if missing, ensures payload indexes."""
    existing = {c.name for c in qdrant.get_collections().collections}
    created = False
    if name not in existing:
        qdrant.create_collection(
            collection_name=name,
            vectors_config=qmodels.VectorParams(size=EMBED_DIM, distance=qmodels.Distance.COSINE),
        )
        created = True
        log.info(f"Collection '{name}' créée")
    for field, schema in indexes or []:
        try:
            qdrant.create_payload_index(collection_name=name, field_name=field, field_schema=schema)
        except Exception:
            pass
    return created


def ensure_models() -> None:
    """Pull embedding and LLM models on Ollama if missing."""
    with httpx.Client(timeout=600) as client:
        try:
            tags = client.get(f"{OLLAMA_URL}/api/tags").json()
            existing = {m["name"] for m in tags.get("models", [])}
        except Exception as e:
            log.error(f"Erreur Ollama: {e}")
            return

        for model in (EMBED_MODEL, LLM_MODEL):
            base = model.split(":")[0]
            if not any(m.startswith(base) for m in existing):
                log.info(f"Téléchargement du modèle {model}...")
                resp = client.post(
                    f"{OLLAMA_URL}/api/pull",
                    json={"name": model, "stream": False},
                    timeout=1800,
                )
                if resp.status_code == 200:
                    log.info(f"Modèle {model} téléchargé")
                else:
                    log.error(f"Erreur téléchargement {model}: {resp.text}")


def embed(text: str) -> list[float]:
    with httpx.Client(timeout=120) as client:
        resp = client.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]


def generate(prompt: str) -> str:
    with httpx.Client(timeout=300) as client:
        resp = client.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": LLM_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2},
            },
        )
        resp.raise_for_status()
        return resp.json()["response"]
