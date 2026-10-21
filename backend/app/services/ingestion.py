"""Document lifecycle: register -> background index -> ready/failed -> delete. Framework-free."""
from __future__ import annotations

import gc
import hashlib
import logging
import time
import uuid
from pathlib import Path

from ..rag.chunking import chunk_pages
from ..rag.parsers import SUPPORTED, ParseError, parse_file
from .factory import Services

log = logging.getLogger("pma.ingest")


class Duplicate(Exception):
    def __init__(self, title: str):
        super().__init__(title)
        self.title = title


class BadUpload(Exception):
    """Message is safe to show to the admin."""


def new_doc_id() -> str:
    return uuid.uuid4().hex[:12]


def check_extension(filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in SUPPORTED:
        raise BadUpload(f"Unsupported file type '{ext or '?'}'. Allowed: {', '.join(sorted(SUPPORTED))}")
    return ext


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def register(svc: Services, *, doc_id: str, path: Path, title: str, kind: str,
             filename: str, uploaded_by: str) -> None:
    """Record a saved file in the DB as 'queued'. Raises Duplicate if identical content exists."""
    sha = sha256_file(path)
    existing = svc.db.doc_by_sha(sha)
    if existing:
        path.unlink(missing_ok=True)
        raise Duplicate(existing["title"])
    svc.db.doc_add(id=doc_id, title=title.strip()[:200] or filename, kind=kind, filename=filename[:255],
                   sha256=sha, size_bytes=path.stat().st_size, uploaded_by=uploaded_by)


def create_note(svc: Services, title: str, text: str, uploaded_by: str) -> str:
    title, text = title.strip(), text.strip()
    if not title or len(text) < 20:
        raise BadUpload("A note needs a title and at least 20 characters of text.")
    doc_id = new_doc_id()
    path = svc.settings.upload_dir / f"{doc_id}.md"
    path.write_text(f"# {title}\n\n{text}\n", encoding="utf-8")
    register(svc, doc_id=doc_id, path=path, title=title, kind="note",
             filename=f"{title[:60]}.md", uploaded_by=uploaded_by)
    return doc_id


def process_document(svc: Services, doc_id: str) -> None:
    """Parse, chunk, embed and store. Runs in a background thread; never raises."""
    row = svc.db.doc_get(doc_id)
    if row is None:
        return
    path = next(iter(svc.settings.upload_dir.glob(f"{doc_id}.*")), None)
    svc.db.doc_update(doc_id, status="processing", error="")
    t0 = time.time()
    log.info("Processing %s started", doc_id)
    try:
        if path is None:
            raise ParseError("Stored file is missing.")
        s = svc.settings
        pages = parse_file(path)
        chunks = chunk_pages(pages, doc_id, s.chunk_chars, s.chunk_chars // 6)
        if not chunks:
            raise ParseError("No usable text found in the document.")
        log.info("Parsed %s: %d pages, %d chunks (%.1fs). Embedding...", doc_id, len(pages), len(chunks),
                 time.time() - t0)
        with svc.ingest_lock:
            svc.store.delete_document(doc_id)
            svc.store.add_chunks(chunks, row["title"])
        svc.db.doc_update(doc_id, status="ready", pages=len(pages), chunks=len(chunks), error="")
        log.info("Indexed %s (%d chunks) in %.1fs", doc_id, len(chunks), time.time() - t0)
    except ParseError as e:
        svc.db.doc_update(doc_id, status="failed", error=str(e)[:500])
    except Exception:
        log.exception("Indexing failed for %s", doc_id)
        svc.db.doc_update(doc_id, status="failed", error="Indexing failed; see the server log.")
    finally:
        gc.collect()  # hand parser/embedding temporaries back before the next request


def delete_document(svc: Services, doc_id: str) -> bool:
    row = svc.db.doc_get(doc_id)
    if row is None:
        return False
    if row["status"] == "processing":
        raise BadUpload("This document is being indexed; try again in a moment.")
    with svc.ingest_lock:
        svc.store.delete_document(doc_id)  # vectors first; if this fails the DB row is kept
    for p in svc.settings.upload_dir.glob(f"{doc_id}.*"):
        p.unlink(missing_ok=True)
    svc.db.doc_delete(doc_id)
    return True
