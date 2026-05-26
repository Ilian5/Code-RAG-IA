"""Postgres connection pool + schema initialization + query helpers.

The 'news' database stores one row per unique article, with metadata + read state.
Qdrant remains source-of-truth for the chunks/vectors; this table is the catalogue.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .core import log


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://n8n:n8n@postgres:5432/news")

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=8, kwargs={"row_factory": dict_row}, open=True)
    return _pool


@contextmanager
def conn():
    with get_pool().connection() as c:
        yield c


SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS articles (
  id                    UUID PRIMARY KEY,
  url                   TEXT UNIQUE NOT NULL,
  title                 TEXT,
  source                TEXT NOT NULL,
  author                TEXT,
  published_at          TIMESTAMPTZ,
  ingested_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  extracted_at          TIMESTAMPTZ,
  content_hash          TEXT,
  word_count            INT,
  reading_time_minutes  INT,
  language              TEXT,
  extraction_method     TEXT,
  summary               TEXT,
  rss_categories        TEXT[],
  n_chunks              INT,
  read_at               TIMESTAMPTZ,
  starred               BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_articles_pub        ON articles(published_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_articles_source     ON articles(source);
CREATE INDEX IF NOT EXISTS idx_articles_hash       ON articles(content_hash);
CREATE INDEX IF NOT EXISTS idx_articles_unread     ON articles(read_at) WHERE read_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_articles_starred    ON articles(starred) WHERE starred = true;
CREATE INDEX IF NOT EXISTS idx_articles_lang       ON articles(language);
CREATE INDEX IF NOT EXISTS idx_articles_title_trgm ON articles USING gin (title gin_trgm_ops);
"""


def init_db() -> None:
    """Idempotent: ensures schema exists. Called at app startup."""
    try:
        with conn() as c:
            with c.cursor() as cur:
                cur.execute(SCHEMA_SQL)
        log.info("Postgres 'news' schema ready")
    except Exception as e:
        log.error(f"Postgres init failed: {e}")
        raise


# ============================================================
# Articles: upsert / read state / queries
# ============================================================

UPSERT_SQL = """
INSERT INTO articles (
  id, url, title, source, author, published_at, ingested_at, extracted_at,
  content_hash, word_count, reading_time_minutes, language, extraction_method,
  summary, rss_categories, n_chunks
) VALUES (
  %(id)s, %(url)s, %(title)s, %(source)s, %(author)s, %(published_at)s,
  %(ingested_at)s, %(extracted_at)s, %(content_hash)s, %(word_count)s,
  %(reading_time_minutes)s, %(language)s, %(extraction_method)s, %(summary)s,
  %(rss_categories)s, %(n_chunks)s
)
ON CONFLICT (url) DO UPDATE SET
  title                = EXCLUDED.title,
  source               = EXCLUDED.source,
  author               = EXCLUDED.author,
  published_at         = COALESCE(EXCLUDED.published_at, articles.published_at),
  ingested_at          = EXCLUDED.ingested_at,
  extracted_at         = EXCLUDED.extracted_at,
  content_hash         = EXCLUDED.content_hash,
  word_count           = EXCLUDED.word_count,
  reading_time_minutes = EXCLUDED.reading_time_minutes,
  language             = COALESCE(EXCLUDED.language, articles.language),
  extraction_method    = EXCLUDED.extraction_method,
  summary              = COALESCE(EXCLUDED.summary, articles.summary),
  rss_categories       = EXCLUDED.rss_categories,
  n_chunks             = EXCLUDED.n_chunks
"""


def upsert_article(row: dict[str, Any]) -> None:
    """Idempotent insert/update keyed by URL."""
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(UPSERT_SQL, row)


def get_article(article_id: str) -> Optional[dict]:
    with conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT * FROM articles WHERE id = %s", (article_id,))
            return cur.fetchone()


def get_article_by_url(url: str) -> Optional[dict]:
    with conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT * FROM articles WHERE url = %s", (url,))
            return cur.fetchone()


def set_read(article_id: str, read: bool) -> Optional[dict]:
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "UPDATE articles SET read_at = %s WHERE id = %s RETURNING *",
                (datetime.utcnow() if read else None, article_id),
            )
            return cur.fetchone()


def set_starred(article_id: str, starred: bool) -> Optional[dict]:
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "UPDATE articles SET starred = %s WHERE id = %s RETURNING *",
                (starred, article_id),
            )
            return cur.fetchone()


def mark_all_read(source: Optional[str] = None) -> int:
    with conn() as c:
        with c.cursor() as cur:
            if source:
                cur.execute(
                    "UPDATE articles SET read_at = now() WHERE read_at IS NULL AND source = %s",
                    (source,),
                )
            else:
                cur.execute("UPDATE articles SET read_at = now() WHERE read_at IS NULL")
            return cur.rowcount


def delete_by_url(url: str) -> int:
    with conn() as c:
        with c.cursor() as cur:
            cur.execute("DELETE FROM articles WHERE url = %s", (url,))
            return cur.rowcount


def delete_by_source(source: str) -> int:
    with conn() as c:
        with c.cursor() as cur:
            cur.execute("DELETE FROM articles WHERE source = %s", (source,))
            return cur.rowcount


def truncate_all() -> int:
    with conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM articles")
            n = cur.fetchone()["n"]
            cur.execute("TRUNCATE TABLE articles")
            return n


def list_articles(
    source: Optional[str] = None,
    since_days: Optional[int] = None,
    unread: bool = False,
    starred: bool = False,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    order: str = "published_at_desc",
) -> tuple[list[dict], int]:
    where, params = [], {}
    if source:
        where.append("source = %(source)s")
        params["source"] = source
    if since_days:
        where.append("published_at >= now() - make_interval(days => %(days)s)")
        params["days"] = since_days
    if unread:
        where.append("read_at IS NULL")
    if starred:
        where.append("starred = true")
    if q:
        # Substring match (case-insensitive). pg_trgm-based similarity was too strict
        # for short queries (default threshold 0.3) — ILIKE is what a search box should do.
        where.append("title ILIKE %(q_like)s")
        params["q_like"] = f"%{q}%"

    sql_where = ("WHERE " + " AND ".join(where)) if where else ""
    order_sql = {
        "published_at_desc": "ORDER BY published_at DESC NULLS LAST",
        "published_at_asc":  "ORDER BY published_at ASC NULLS LAST",
        "ingested_at_desc":  "ORDER BY ingested_at DESC",
    }.get(order, "ORDER BY published_at DESC NULLS LAST")

    with conn() as c:
        with c.cursor() as cur:
            cur.execute(f"SELECT count(*) AS n FROM articles {sql_where}", params)
            total = cur.fetchone()["n"]
            params["limit"], params["offset"] = limit, offset
            cur.execute(
                f"SELECT * FROM articles {sql_where} {order_sql} LIMIT %(limit)s OFFSET %(offset)s",
                params,
            )
            rows = cur.fetchall()
    return rows, total


def sources_with_counts() -> list[dict]:
    with conn() as c:
        with c.cursor() as cur:
            cur.execute("""
                SELECT source,
                       count(*) AS total,
                       count(*) FILTER (WHERE read_at IS NULL) AS unread,
                       max(published_at) AS last_published
                FROM articles
                GROUP BY source
                ORDER BY total DESC
            """)
            return cur.fetchall()


def global_stats() -> dict:
    with conn() as c:
        with c.cursor() as cur:
            cur.execute("""
                SELECT count(*)                                  AS total,
                       count(*) FILTER (WHERE read_at IS NULL)   AS unread,
                       count(*) FILTER (WHERE starred = true)    AS starred,
                       coalesce(sum(word_count), 0)              AS total_words
                FROM articles
            """)
            base = cur.fetchone()
            cur.execute("SELECT language, count(*) AS n FROM articles GROUP BY language")
            languages = {(r["language"] or "unknown"): r["n"] for r in cur.fetchall()}
            cur.execute("""
                SELECT date_trunc('day', ingested_at)::date AS day, count(*) AS n
                FROM articles
                WHERE ingested_at >= now() - interval '30 days'
                GROUP BY day ORDER BY day
            """)
            daily = [{"day": r["day"].isoformat(), "count": r["n"]} for r in cur.fetchall()]
    return {**base, "languages": languages, "daily_ingestion_30d": daily}
