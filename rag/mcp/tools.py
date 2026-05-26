"""MCP tools exposed by the tech-news server.

Read-only structured queries on Postgres + a passthrough to the RAG semantic search.

Note: this module deliberately does NOT use `from __future__ import annotations`.
The MCP SDK introspects parameter annotations at decoration time and stringified
annotations break its `issubclass(...)` check.
"""

import os
from datetime import datetime
from typing import Any, Optional, Union

import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def _to_int(v, default=None):
    """Coerce LLM-emitted strings into integers — small models (llama3.2:3b)
    often emit numeric tool arguments as strings."""
    if v is None or v == "":
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _to_bool(v, default=False):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes", "y")
    return default


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://n8n:n8n@postgres:5432/news")
RAG_API_URL = os.getenv("RAG_API_URL", "http://rag-api:8000")

_pool: Optional[ConnectionPool] = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=4, kwargs={"row_factory": dict_row}, open=True)
    return _pool


def _serialize(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def register_all(mcp) -> None:
    @mcp.tool()
    def list_articles(
        source: str = "",
        since_days: int = 0,
        unread_only: bool = False,
        starred_only: bool = False,
        limit: int = 20,
    ) -> list:
        """List indexed tech articles with optional filters.

        Args:
            source: filter by source name (e.g. "Cloudflare Blog"). Empty string = all sources.
            since_days: only articles published in the last N days. 0 = no time filter.
            unread_only: only articles not yet marked as read
            starred_only: only starred articles
            limit: max number of articles to return (default 20, max 100)
        """
        limit = max(1, min(100, _to_int(limit, 20)))
        days = _to_int(since_days, 0)
        unread_only = _to_bool(unread_only)
        starred_only = _to_bool(starred_only)
        where = []
        params = {}
        if source:
            where.append("source = %(source)s"); params["source"] = source
        if days > 0:
            where.append("published_at >= now() - make_interval(days => %(d)s)"); params["d"] = days
        if unread_only:
            where.append("read_at IS NULL")
        if starred_only:
            where.append("starred = true")
        params["limit"] = limit
        sql_where = "WHERE " + " AND ".join(where) if where else ""
        sql = f"""
            SELECT id, url, title, source, author, published_at, word_count,
                   reading_time_minutes, language, read_at IS NULL AS unread, starred
            FROM articles {sql_where}
            ORDER BY published_at DESC NULLS LAST
            LIMIT %(limit)s
        """
        with _get_pool().connection() as c, c.cursor() as cur:
            cur.execute(sql, params)
            return [_serialize(r) for r in cur.fetchall()]

    @mcp.tool()
    def count_by_source() -> dict:
        """Return per-source article counts (total / unread)."""
        sql = """
            SELECT source,
                   count(*) AS total,
                   count(*) FILTER (WHERE read_at IS NULL) AS unread
            FROM articles GROUP BY source ORDER BY total DESC
        """
        with _get_pool().connection() as c, c.cursor() as cur:
            cur.execute(sql)
            return {r["source"]: {"total": r["total"], "unread": r["unread"]} for r in cur.fetchall()}

    @mcp.tool()
    def count_unread(source: str = "") -> int:
        """Number of unread articles. Pass source to filter by source name, empty = all."""
        sql = "SELECT count(*) AS n FROM articles WHERE read_at IS NULL"
        params: dict = {}
        if source:
            sql += " AND source = %(source)s"; params["source"] = source
        with _get_pool().connection() as c, c.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()["n"]

    @mcp.tool()
    def recent_articles(limit: int = 10) -> list:
        """Most recently published articles across all sources."""
        return list_articles(limit=_to_int(limit, 10))

    @mcp.tool()
    def articles_in_date_range(
        date_from: str, date_to: str, source: str = ""
    ) -> list:
        """Articles published between two ISO dates (inclusive).

        Args:
            date_from: ISO date (YYYY-MM-DD or full ISO timestamp)
            date_to: ISO date
            source: optional source filter, empty string = all
        """
        sql = """
            SELECT id, url, title, source, author, published_at, word_count, language
            FROM articles
            WHERE published_at >= %(from)s::timestamptz
              AND published_at <= %(to)s::timestamptz
        """
        params = {"from": date_from, "to": date_to}
        if source:
            sql += " AND source = %(source)s"; params["source"] = source
        sql += " ORDER BY published_at DESC LIMIT 200"
        with _get_pool().connection() as c, c.cursor() as cur:
            cur.execute(sql, params)
            return [_serialize(r) for r in cur.fetchall()]

    @mcp.tool()
    def get_article(url: str) -> dict:
        """Fetch one article by URL — includes the reconstructed markdown."""
        with _get_pool().connection() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM articles WHERE url = %s", (url,))
            row = cur.fetchone()
            if not row:
                return {"error": "not found"}
        # Use the RAG API to reconstruct the markdown from Qdrant
        try:
            r = httpx.get(f"{RAG_API_URL}/api/articles/by-url", params={"url": url}, timeout=10)
            if r.status_code == 200:
                row["markdown"] = r.json().get("markdown", "")
        except Exception:
            row["markdown"] = ""
        return _serialize(row)

    @mcp.tool()
    def retrieve_articles(question: str, top_k: int = 5) -> list:
        """Recherche sémantique : récupère les extraits d'articles les plus pertinents
        pour une question en langage naturel. Renvoie chunks bruts (titre, source, URL,
        texte), pas de génération LLM. À utiliser pour TOUTE question ouverte / sémantique.

        Args:
            question: la question utilisateur en français ou anglais
            top_k: nombre de chunks (entier, défaut 5, max 15)
        """
        k = max(1, min(15, _to_int(top_k, 5)))
        r = httpx.post(
            f"{RAG_API_URL}/api/articles/retrieve",
            json={"question": question, "top_k": k},
            timeout=30,
        )
        r.raise_for_status()
        return r.json().get("chunks", [])

    @mcp.tool()
    def recent_articles_with_excerpts(since_days: int = 1, limit: int = 10) -> list:
        """Articles récents AVEC le résumé RSS et un extrait du contenu.

        À utiliser quand l'utilisateur demande un APERÇU / RÉSUMÉ / DIGEST des dernières
        actualités. Renvoie pour chaque article : titre, source, URL, date,
        summary (résumé RSS court) ET first_chunk (premier extrait du contenu).
        Permet de synthétiser une vraie revue de presse, pas juste une liste d'URLs.

        Args:
            since_days: période (jours), défaut 1 (= 24h)
            limit: nombre max d'articles, défaut 10, max 20
        """
        days = max(1, _to_int(since_days, 1))
        limit = max(1, min(20, _to_int(limit, 10)))
        sql = """
            SELECT id, url, title, source, published_at, summary
            FROM articles
            WHERE published_at >= now() - make_interval(days => %(d)s)
            ORDER BY published_at DESC
            LIMIT %(limit)s
        """
        with _get_pool().connection() as c, c.cursor() as cur:
            cur.execute(sql, {"d": days, "limit": limit})
            rows = cur.fetchall()

        # Fetch first chunk of each article from Qdrant via rag-api
        out = []
        for row in rows:
            row = _serialize(row)
            row["first_chunk"] = ""
            try:
                r = httpx.get(
                    f"{RAG_API_URL}/api/articles/by-url",
                    params={"url": row["url"]},
                    timeout=5,
                )
                if r.status_code == 200:
                    md = r.json().get("markdown", "")
                    # First ~500 chars excerpt
                    row["first_chunk"] = md[:600].strip()
            except Exception:
                pass
            out.append(row)
        return out
