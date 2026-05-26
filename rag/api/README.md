# RAG API — local stack

FastAPI + Qdrant + Ollama. Two ingestion paths:

- **PDFs** — watcher inotify on `INBOX_DIR`, conversion via `pymupdf4llm`.
- **Articles RSS** — pushed by n8n, extraction via `trafilatura`.

Tout 100% local, aucune donnée ne quitte le serveur.

## Layout

```
main.py                 # uvicorn entry point + lifespan + router wiring
api/
  core.py               # Qdrant + Ollama clients, embed, generate, logging
  chunking.py           # smart_chunk: structural markdown chunking
  pdfs.py               # PDF pipeline (PyMuPDF) + watchdog
  articles.py           # Article pipeline (trafilatura → smart_chunk → upsert)
  routes_admin.py       # /api/health, /api/overview, /api/config, /api/logs
  routes_pdfs.py        # /api/{files,upload,query,preview-md,...}
  routes_articles.py    # /api/articles/*
static/                 # dashboard (HTML + CSS + JS, sober light theme)
tests/
  test_articles.py      # standalone test runner with stubbed Qdrant/Ollama
```

## Article pipeline

1. n8n posts `{url, title, content_html, source, author, published_at, summary_rss}` to `POST /api/articles/ingest`.
2. `trafilatura.extract(html, output_format="markdown")` strips nav / footer / scripts / boilerplate.
3. If extracted markdown < 200 chars → fall back to the RSS `summary_rss`. Tagged `extraction_method=rss_summary`.
4. `sha256(markdown)` → `content_hash`. Cross-URL dedup: a hash already attached to another URL → status `duplicate`, no insert.
5. `smart_chunk` splits by markdown headings (same logic as PDFs).
6. Embeddings via `nomic-embed-text` (768d) → Qdrant `articles` collection.

UUIDs Qdrant : `uuid5(URL_NAMESPACE, "{url}#{chunk_index}")`. Idempotent: re-ingesting the same URL upserts in place.

Indexed payload fields (KEYWORD): `source`, `url`, `content_hash`, `language`. `published_at` is indexed as DATETIME for `since_days` filtering.

## Endpoints

| Path | Method | Purpose |
|---|---|---|
| `/api/articles/ingest` | POST | Ingest one article |
| `/api/articles/ingest-batch` | POST | Ingest a list |
| `/api/articles/query` | POST | Semantic search + LLM synthesis |
| `/api/articles/list` | GET | Paginated unique-article listing |
| `/api/articles/sources` | GET | Counts per source |
| `/api/articles/stats` | GET | Counts + total words + language histogram |
| `/api/articles/preview-extraction` | GET | Fetch + extract a URL without storing (debug) |
| `/api/articles/by-url` | GET | Full payload + reconstructed markdown |
| `/api/articles/by-url` | DELETE | Drop one article |
| `/api/articles/by-source` | DELETE | Drop a whole source |
| `/api/articles/duplicates` | GET | Audit content_hash collisions |
| `/api/articles/clear` | DELETE | Wipe the collection |

## Tests

```bash
docker compose -f /opt/n8n/docker-compose.yml run --rm rag-api python tests/test_articles.py
```

Stubs Qdrant in-memory and `embed`/`generate`. Validates extraction, deduplication, idempotence, chunking, and full payload shape.

## Configuration (env vars)

`OLLAMA_URL`, `QDRANT_URL`, `LLM_MODEL`, `EMBED_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`, `INBOX_DIR`, `PROCESSED_DIR`.
