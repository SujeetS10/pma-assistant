"""Page- and structure-aware chunking that never splits display math ($$...$$)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .parsers import Page

_HEADING = re.compile(
    r"^(#{1,6}\s+.+|(?:chapter|section|unit|module)\s+\d+[.:)\s].*|\d+(?:\.\d+)+\s+\S.*)$",
    re.I,
)


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    text: str
    page_start: int | None
    page_end: int | None
    section: str
    index: int


@dataclass
class _Block:
    text: str
    page: int | None
    section: str


def split_blocks(text: str) -> list[str]:
    """Split on blank lines, keeping $$...$$ display-math blocks whole."""
    blocks: list[str] = []
    cur: list[str] = []
    in_math = False
    for line in text.splitlines():
        if line.count("$$") % 2 == 1:
            in_math = not in_math
        if not line.strip() and not in_math:
            if cur:
                blocks.append("\n".join(cur).strip())
                cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur).strip())
    return [b for b in blocks if b]


def _split_long(text: str, limit: int) -> list[str]:
    """Split an oversized block on sentence boundaries, then hard-split on words."""
    if len(text) <= limit:
        return [text]
    if "$$" in text:  # keep math intact even if a little over the limit
        return [text]
    pieces: list[str] = []
    cur = ""
    for sent in re.split(r"(?<=[.!?])\s+", text):
        while len(sent) > limit:
            cut = sent.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.append(sent[:cut])
            sent = sent[cut:].lstrip()
        if cur and len(cur) + 1 + len(sent) > limit:
            pieces.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        pieces.append(cur)
    return pieces


def chunk_pages(
    pages: list[Page], doc_id: str, max_chars: int = 1200, overlap_chars: int = 200
) -> list[Chunk]:
    """Group blocks into chunks of ~max_chars, tracking page range and section."""
    blocks: list[_Block] = []
    section = ""
    for pg in pages:
        for b in split_blocks(pg.text):
            first_line = b.splitlines()[0].strip()
            if _HEADING.match(first_line) and len(first_line) <= 120:
                section = first_line.lstrip("# ").strip()
            for piece in _split_long(b, max_chars):
                blocks.append(_Block(piece, pg.page, section))

    chunks: list[Chunk] = []
    cur: list[_Block] = []

    def size(bs: list[_Block]) -> int:
        return sum(len(b.text) for b in bs) + 2 * max(len(bs) - 1, 0)

    def flush() -> None:
        if not cur:
            return
        text = "\n\n".join(b.text for b in cur)
        nums = [b.page for b in cur if b.page is not None]
        idx = len(chunks)
        cid = hashlib.sha1(f"{doc_id}|{idx}|{text}".encode()).hexdigest()[:16]
        chunks.append(
            Chunk(
                cid,
                doc_id,
                text,
                min(nums) if nums else None,
                max(nums) if nums else None,
                cur[0].section,
                idx,
            )
        )

    for b in blocks:
        if cur and size(cur) + 2 + len(b.text) > max_chars:
            flush()
            tail = cur[-1]
            # Overlap by whole block so equations/sentences are never cut mid-way.
            cur = [tail] if len(tail.text) <= overlap_chars and tail.section == b.section else []
        cur.append(b)
    flush()
    return chunks
