# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A self-hosted, 100% local tech-news aggregator + RAG stack running on a single server. Five sub-apps that share one Docker Compose network. `/opt` is **not** a git repo — it's the deployment root. Code lives in three trees:

- [n8n/](n8n/) — Docker Compose + Caddy reverse proxy + `.env` (the orchestrator for the entire stack, despite the directory name).
- [rag/api/](rag/api/) — FastAPI backend (`rag-api` service). Ingests PDFs and RSS articles, exposes search + CRUD.
- [rag/mcp/](rag/mcp/) — MCP server (`mcp-server` service). Read-only structured tools over Postgres + passthrough to RAG semantic search.
- [rag/news/](rag/news/) — SvelteKit static frontend at `news.leoharlay.dev`, served by Caddy from `/srv/news`.

The Compose file at [n8n/docker-compose.yml](n8n/docker-compose.yml) is the single source of truth for what runs.

## Architecture

```
                            Caddy (basic_auth, TLS)
                              │
        ┌─────────┬───────────┼─────────────┬─────────┬─────────┐
        ▼         ▼           ▼             ▼         ▼         ▼
      n8n     rag-api    mcp-server    SvelteKit  Adminer   Qdrant
       │         │           │            (static)    │       │
       ▼         ▼           ▼                        ▼       ▼
   Postgres   Ollama       Postgres                Postgres  (vectors)
              + Qdrant     + rag-api (HTTP)
              + Postgres
```

**Two ingestion paths into the RAG, both ending up in Qdrant + Postgres:**

1. **PDFs** — drop into `/opt/rag/inbox` → watchdog inotify in [rag/api/api/pdfs.py](rag/api/api/pdfs.py) → `pymupdf4llm` → `smart_chunk` → embed (nomic-embed-text) → Qdrant `documents` collection → moved to `/opt/rag/processed`.
2. **RSS articles** — n8n RSS workflow posts to `POST /api/articles/ingest` → trafilatura extracts markdown → `smart_chunk` → embed → Qdrant `articles` collection + mirror row into Postgres `news.articles`.

**Storage split — important:**
- **Qdrant** is the source of truth for content (chunks, vectors, full reconstructable markdown).
- **Postgres** `news.articles` is a catalogue: one row per unique URL with metadata + read/starred state. Lives in a separate database (`news`) from n8n's own DB (`n8n`), both on the same Postgres instance.
- On rag-api boot, [rag/api/main.py:22](rag/api/main.py#L22) `backfill_news_from_qdrant` scrolls Qdrant and re-populates Postgres if rows are missing. Postgres can be wiped and recover from Qdrant; the reverse is not true.

**Idempotency contract:**
- Article Qdrant IDs are `uuid5(URL_NAMESPACE, "{url}#{chunk_index}")` — re-ingesting the same URL upserts in place.
- Postgres row IDs are `uuid5(URL_NAMESPACE, url)` (no chunk suffix) — same article = same row.
- Cross-URL dedup uses `sha256(markdown)`: if another URL already has that hash, the new URL is rejected with `status=duplicate` and **not** inserted.

**Routing (Caddyfile):** the `news.leoharlay.dev` host routes `/api/chat` → n8n webhook (`/webhook/chat-news`), all other `/api/*` → `rag-api:8000`, everything else → SvelteKit static build. Frontend code calls relative paths like `/api/articles/list`.

## Common commands

All commands assume cwd anywhere; paths are absolute.

**Bring the stack up / down:**
```bash
docker compose -f /opt/n8n/docker-compose.yml up -d
docker compose -f /opt/n8n/docker-compose.yml down
docker compose -f /opt/n8n/docker-compose.yml logs -f rag-api    # follow one service
docker compose -f /opt/n8n/docker-compose.yml restart rag-api    # after editing rag/api/
docker compose -f /opt/n8n/docker-compose.yml up -d --build rag-api mcp-server   # after Dockerfile/req changes
```

**Run the article pipeline test (stubbed Qdrant/Ollama, no real services needed):**
```bash
docker compose -f /opt/n8n/docker-compose.yml run --rm rag-api python tests/test_articles.py
```

**SvelteKit frontend** (in [rag/news/](rag/news/)):
```bash
npm run dev       # local dev server
npm run build     # writes to build/ — Caddy serves this directly via the bind mount
npm run check     # svelte-check + tsc
```
After `npm run build`, Caddy picks up the new files immediately (bind-mounted read-only at `/srv/news`).

**Ad-hoc DB / Qdrant inspection:**
- Adminer: `https://db.leoharlay.dev` (Postgres GUI).
- Qdrant dashboard: `https://qdrant.leoharlay.dev/dashboard`.
- Both behind the shared `BASIC_AUTH_RAG_*` credentials from [n8n/.env](n8n/.env).

## Things that will bite you

- **No `from __future__ import annotations` in [rag/mcp/tools.py](rag/mcp/tools.py).** The MCP SDK introspects parameter annotations at decoration time and stringified annotations break its `issubclass(...)` check. Other files are free to use it.
- **Small-model tool args arrive as strings.** `llama3.2:3b` emits numeric MCP tool args as strings — that's why `tools.py` has `_to_int`/`_to_bool` coercers around every numeric arg.
- **The `summary_rss` field has an alias.** The Pydantic model [ArticleIngestReq](rag/api/api/articles.py#L32) uses `Field(alias="summary")` because n8n's RSS node calls the field `summary`. The model also accepts both `content_html` and the legacy `content` for the HTML body.
- **Two ingestion endpoints, two contracts.** `/api/articles/ingest` takes raw HTML and runs trafilatura. `/api/articles/retrieve` (raw chunks, no LLM) is for agentic callers; `/api/articles/query` runs LLM synthesis on top. The MCP `retrieve_articles` tool hits `/retrieve`, not `/query`.
- **rag-api lifespan boot is async and threaded** ([rag/api/main.py:70](rag/api/main.py#L70)): collection creation, model pulling, Postgres init, backfill, and the inotify watcher all run on a background thread so the HTTP server comes up immediately. Don't move that work back onto the main async loop — model pulls can take ~30min on first boot.
- **Both rag-api and mcp-server hold their own Postgres connection pool** to the `news` database. They're separate processes; don't try to share one.
- **Caddy reads `/opt/rag/news/build` read-only** — you must `npm run build` for changes to be served; `npm run dev` only works when accessed locally on the dev port.
- **`.env` is at [n8n/.env](n8n/.env)**, not at `/opt/.env`. All Compose variable interpolation reads from there.

## Configuration

Env vars consumed by rag-api (defaults shown):
- `OLLAMA_URL=http://ollama:11434`, `QDRANT_URL=http://qdrant:6333`
- `LLM_MODEL=llama3.2:3b`, `EMBED_MODEL=nomic-embed-text` (768d)
- `CHUNK_SIZE=800`, `CHUNK_OVERLAP=100`, `TOP_K=5`
- `INBOX_DIR=/data/inbox`, `PROCESSED_DIR=/data/processed` (bind-mounted from `/opt/rag/inbox`, `/opt/rag/processed`)
- `DATABASE_URL=postgresql://n8n:n8n@postgres:5432/news`

mcp-server consumes `DATABASE_URL` and `RAG_API_URL=http://rag-api:8000`.

All values are wired through [n8n/docker-compose.yml](n8n/docker-compose.yml) from [n8n/.env](n8n/.env).
