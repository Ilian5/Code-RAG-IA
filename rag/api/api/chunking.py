"""Structural markdown chunking: splits by headings, then paragraphs, then size."""

from __future__ import annotations

import re

from .core import CHUNK_OVERLAP, CHUNK_SIZE


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def split_by_headings(md: str) -> list[tuple[str, int, str]]:
    matches = list(HEADING_RE.finditer(md))
    if not matches:
        return [("", 0, md.strip())] if md.strip() else []

    sections: list[tuple[str, int, str]] = []
    title_stack: list[tuple[int, str]] = []

    if matches[0].start() > 0:
        preface = md[: matches[0].start()].strip()
        if preface:
            sections.append(("(préface)", 0, preface))

    for i, m in enumerate(matches):
        level = len(m.group(1))
        title = m.group(2).strip()

        title_stack = [(lvl, t) for lvl, t in title_stack if lvl < level]
        title_stack.append((level, title))
        hierarchical_title = " > ".join(t for _, t in title_stack)

        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        content = md[start:end].strip()
        if content:
            sections.append((hierarchical_title, level, content))

    return sections


def split_by_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def split_fixed_size(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + size
        if end < len(text):
            slice_end = text.rfind(". ", start + size // 2, end)
            if slice_end > 0:
                end = slice_end + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = end - overlap
    return [c for c in chunks if c]


def smart_chunk(md: str) -> list[dict]:
    """Splits markdown into chunks that respect heading structure.

    Returns: [{"text", "heading", "level"}, ...]
    """
    sections = split_by_headings(md)
    chunks: list[dict] = []

    for heading, level, content in sections:
        prefix = f"[Section: {heading}]\n" if heading else ""

        if len(content) <= CHUNK_SIZE:
            chunks.append({"text": (prefix + content).strip(), "heading": heading, "level": level})
            continue

        paragraphs = split_by_paragraphs(content)
        buffer = ""
        for para in paragraphs:
            if len(buffer) + len(para) + 2 <= CHUNK_SIZE:
                buffer = (buffer + "\n\n" + para).strip() if buffer else para
            else:
                if buffer:
                    chunks.append({"text": (prefix + buffer).strip(), "heading": heading, "level": level})
                    buffer = ""
                if len(para) > CHUNK_SIZE:
                    for sub in split_fixed_size(para):
                        chunks.append({"text": (prefix + sub).strip(), "heading": heading, "level": level})
                else:
                    buffer = para
        if buffer:
            chunks.append({"text": (prefix + buffer).strip(), "heading": heading, "level": level})

    return [c for c in chunks if c["text"]]
