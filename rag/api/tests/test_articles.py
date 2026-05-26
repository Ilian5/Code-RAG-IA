"""End-to-end test of the article pipeline with Qdrant/Ollama stubbed.

Run inside the rag-api container (or any environment with trafilatura, pydantic,
qdrant-client installed):

    docker compose run --rm rag-api python tests/test_articles.py
    # or, on a workstation:
    python tests/test_articles.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Make the package importable when run as a script.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Avoid hitting any real service during import.
os.environ.setdefault("OLLAMA_URL", "http://stub:11434")
os.environ.setdefault("QDRANT_URL", "http://stub:6333")


# ============================================================
# Stub setup — must run before importing the pipeline modules
# ============================================================

class FakeQdrant:
    """Minimal in-memory Qdrant stub. Stores points keyed by id."""
    def __init__(self):
        self.points: dict[str, dict] = {}

    def get_collections(self):
        return MagicMock(collections=[MagicMock(name="articles"), MagicMock(name="documents")])

    def create_collection(self, **kw): return None
    def create_payload_index(self, **kw): return None
    def get_collection(self, name):
        return MagicMock(points_count=len(self.points))
    def delete_collection(self, name):
        self.points.clear()

    def upsert(self, collection_name, points):
        for p in points:
            self.points[p.id] = {"id": p.id, "vector": p.vector, "payload": dict(p.payload)}

    def delete(self, collection_name, points_selector):
        # Read filter -> drop matching points.
        f = points_selector.filter
        must = list(getattr(f, "must", []) or [])
        if not must:
            self.points.clear(); return
        cond = must[0]
        key = cond.key
        wanted = cond.match.value
        self.points = {pid: pt for pid, pt in self.points.items() if pt["payload"].get(key) != wanted}

    def scroll(self, collection_name, scroll_filter=None, limit=256, with_payload=True, with_vectors=False, offset=None):
        items = list(self.points.values())
        if scroll_filter is not None:
            must = list(getattr(scroll_filter, "must", []) or [])
            for cond in must:
                key, val = cond.key, cond.match.value
                items = [it for it in items if it["payload"].get(key) == val]
        results = [MagicMock(id=it["id"], payload=it["payload"]) for it in items[:limit]]
        return results, None

    def search(self, collection_name, query_vector, query_filter=None, limit=5):
        items = list(self.points.values())
        # Fake similarity score = 1.0
        return [MagicMock(id=it["id"], payload=it["payload"], score=1.0) for it in items[:limit]]

    def count(self, collection_name, count_filter):
        must = list(getattr(count_filter, "must", []) or [])
        items = list(self.points.values())
        for cond in must:
            items = [it for it in items if it["payload"].get(cond.key) == cond.match.value]
        return MagicMock(count=len(items))


# Patch core BEFORE article module imports it
import api.core as core
fake_qdrant = FakeQdrant()
core.qdrant = fake_qdrant
core.embed = lambda text: [0.1] * core.EMBED_DIM
core.generate = lambda prompt: "stub-answer"

# Now import the pipeline. articles.py imports `qdrant` and `embed` from core,
# so we re-import with the patches applied.
import importlib
import api.articles
importlib.reload(api.articles)
from api.articles import (
    ArticleIngestReq,
    article_id,
    content_hash,
    derive_metrics,
    extract_article_markdown,
    ingest_article,
)
from api.chunking import smart_chunk


# ============================================================
# Tests
# ============================================================

FAILURES: list[str] = []


def assert_eq(actual, expected, msg=""):
    if actual != expected:
        line = sys._getframe(1).f_lineno
        FAILURES.append(f"L{line} {msg}: expected {expected!r}, got {actual!r}")


def assert_true(cond, msg=""):
    if not cond:
        line = sys._getframe(1).f_lineno
        FAILURES.append(f"L{line} {msg}")


def test_extract_strips_boilerplate():
    html = """
    <html><body>
    <nav>Home | About | Subscribe to newsletter</nav>
    <header><h1>Site Name</h1></header>
    <article>
      <h1>Quantum Cryptography</h1>
      <h2>Why now?</h2>
      <p>Post-quantum cryptography is becoming critical. Researchers have worked on it for over a decade.
      Standardisation is finally bearing fruit and modern protocols must adapt.</p>
      <h2>Standards</h2>
      <p>NIST finalised three standards in 2024: ML-KEM, ML-DSA, and SLH-DSA.
      They are believed secure against both classical and quantum adversaries.</p>
    </article>
    <aside>Related: foo bar</aside>
    <footer>Copyright. Subscribe to newsletter for more!</footer>
    <script>console.log('boilerplate')</script>
    </body></html>
    """
    md, _meta = extract_article_markdown(html)
    assert_true(len(md) > 200, "markdown too short")
    assert_true("Subscribe to newsletter" not in md, "newsletter boilerplate leaked")
    assert_true("console.log" not in md, "script content leaked")
    assert_true("Why now?" in md, "section headings missing")
    assert_true("Standards" in md, "second section missing")


def test_short_html_falls_back_to_summary():
    fake_qdrant.points.clear()
    req = ArticleIngestReq(
        url="https://example.com/short",
        title="Short",
        content_html="<html><body><p>tiny</p></body></html>",
        source="test",
        summary_rss="A reasonable RSS summary that exceeds the minimum extracted threshold so we still ingest something useful for search even when the HTML body is empty or trafilatura fails to find anything substantive.",
    )
    res = ingest_article(req)
    assert_eq(res.get("status"), "ok", "should succeed via fallback")
    assert_eq(res.get("extraction_method"), "rss_summary", "should mark fallback method")


def test_content_hash_dedup():
    fake_qdrant.points.clear()
    html = """<html><body><article><h1>Same Article</h1>
      <p>This text is identical across two URLs and is long enough to satisfy the minimum
      extraction threshold imposed by the article ingestion pipeline. We need to repeat this
      to make sure trafilatura emits enough markdown content for the validation to pass.</p>
      <p>More content to ensure the markdown body crosses the 200-character threshold easily and is
      treated as a real extraction rather than falling through to the RSS summary fallback path.</p>
    </article></body></html>"""
    r1 = ingest_article(ArticleIngestReq(url="https://a.com/x", content_html=html, source="A"))
    r2 = ingest_article(ArticleIngestReq(url="https://b.com/y", content_html=html, source="B"))
    assert_eq(r1.get("status"), "ok", "first ingestion should succeed")
    assert_eq(r2.get("status"), "duplicate", "second URL with same content must be flagged duplicate")
    assert_eq(r2.get("canonical_url"), "https://a.com/x", "canonical URL should point to first")


def test_uuid_v5_idempotent():
    a = article_id("https://x.com/a", 0)
    b = article_id("https://x.com/a", 0)
    c = article_id("https://x.com/a", 1)
    assert_eq(a, b, "same URL+chunk should produce same UUID")
    assert_true(a != c, "different chunk index should produce different UUID")


def test_idempotence_upsert_replaces():
    fake_qdrant.points.clear()
    html = """<html><body><article><h1>Idempotence Test</h1>
      <p>This content is long enough to pass extraction validation thresholds and trigger
      the normal ingest path. We are checking that ingesting the same URL twice does not
      accumulate duplicate chunks but rather upserts in place via the deterministic UUIDs.</p>
      <p>Some additional content to push markdown length past the minimum threshold easily.</p>
    </article></body></html>"""
    req = ArticleIngestReq(url="https://x.com/ide", content_html=html, source="X")
    r1 = ingest_article(req)
    n1 = len(fake_qdrant.points)
    r2 = ingest_article(req)
    n2 = len(fake_qdrant.points)
    assert_eq(r1.get("status"), "ok", "first OK")
    assert_eq(r2.get("status"), "ok", "second OK (re-ingest same URL)")
    assert_eq(n1, n2, "point count must not grow on re-ingest")


def test_smart_chunk_respects_headings():
    md = "# Title\n\nIntro text.\n\n## Section A\n\nA content paragraph.\n\n## Section B\n\nB content paragraph."
    chunks = smart_chunk(md)
    headings = {c["heading"] for c in chunks}
    assert_true(any("Section A" in h for h in headings), "Section A heading missing")
    assert_true(any("Section B" in h for h in headings), "Section B heading missing")


def test_pipeline_full_payload():
    fake_qdrant.points.clear()
    html = """<html><body><article><h1>Full Pipeline</h1>
      <h2>Intro</h2>
      <p>This article has enough content to pass extraction and produce real metadata,
      with a clear headed structure that smart_chunk should preserve when slicing into
      embedding chunks. We want to verify that the resulting payload exposes every field
      we need for the dashboard to render reading time, word count, and language tags.</p>
      <h2>Body</h2>
      <p>More content adding meaningful length and a second section to check that the
      heading stack is rebuilt correctly across chunks rather than collapsed into one.</p>
    </article></body></html>"""
    res = ingest_article(ArticleIngestReq(
        url="https://demo.test/full",
        title="Full Pipeline",
        content_html=html,
        source="DemoSource",
        author="Alice",
        published_at="2025-01-15T10:00:00Z",
        summary_rss="A short RSS blurb",
    ))
    assert_eq(res.get("status"), "ok")
    assert_true(res.get("chunks") >= 1, "should have at least one chunk")
    assert_true(res.get("word_count") > 0, "word count should be positive")
    assert_true(res.get("reading_time_minutes") >= 1, "reading time >= 1")
    # Inspect a stored payload
    any_point = next(iter(fake_qdrant.points.values()))
    p = any_point["payload"]
    for field in ("url", "title", "source", "author", "published_at", "ingested_at",
                  "extracted_at", "content_hash", "word_count", "reading_time_minutes",
                  "extraction_method", "chunk_index", "n_chunks", "text", "heading"):
        assert_true(field in p, f"payload missing field: {field}")
    assert_eq(p["source"], "DemoSource")
    assert_eq(p["author"], "Alice")
    assert_eq(p["extraction_method"], "trafilatura")
    assert_true(len(p["content_hash"]) == 64, "content_hash should be sha256 hex")


def test_metrics_calculation():
    md = " ".join(["word"] * 400)  # 400 words
    wc, rt = derive_metrics(md)
    assert_eq(wc, 400)
    assert_eq(rt, 2)


def test_content_hash_stable():
    a = content_hash("hello world")
    b = content_hash("hello world")
    c = content_hash("hello worlD")
    assert_eq(a, b, "same input → same hash")
    assert_true(a != c, "different input → different hash")


# ============================================================
# Runner
# ============================================================

TESTS = [
    ("extract_strips_boilerplate", test_extract_strips_boilerplate),
    ("short_html_falls_back_to_summary", test_short_html_falls_back_to_summary),
    ("content_hash_dedup", test_content_hash_dedup),
    ("uuid_v5_idempotent", test_uuid_v5_idempotent),
    ("idempotence_upsert_replaces", test_idempotence_upsert_replaces),
    ("smart_chunk_respects_headings", test_smart_chunk_respects_headings),
    ("pipeline_full_payload", test_pipeline_full_payload),
    ("metrics_calculation", test_metrics_calculation),
    ("content_hash_stable", test_content_hash_stable),
]


def main():
    for name, fn in TESTS:
        before = len(FAILURES)
        try:
            fn()
        except Exception as e:
            FAILURES.append(f"{name}: exception {type(e).__name__}: {e}")
        if len(FAILURES) == before:
            print(f"OK   {name}")
        else:
            print(f"FAIL {name}")

    print("-" * 50)
    if not FAILURES:
        print(f"{len(TESTS)} tests OK")
        return 0
    print(f"{len(FAILURES)} failure(s):")
    for f in FAILURES:
        print(f"  - {f}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
