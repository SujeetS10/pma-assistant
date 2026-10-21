"""Lightweight vector store: SQLite for text + metadata + vectors, NumPy for cosine search.

Replaces ChromaDB (which pulls in a large dependency tree and loads an HNSW index into RAM). A course's
notes are a few thousand chunks at most, so exact brute-force search is instant and gives identical
results to cosine similarity. Only the vectors are cached in memory (384 floats ~ 1.5 KB per chunk);
chunk text is read from disk for the few hits returned.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from .chunking import Chunk
from .embedding import Embedder

log = logging.getLogger("pma.vectors")


@dataclass
class Hit:
    chunk_id: str
    doc_id: str
    doc_title: str
    text: str
    page_start: int | None
    page_end: int | None
    section: str
    score: float  # cosine similarity, higher is better


SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chunk_id TEXT NOT NULL UNIQUE,
  doc_id TEXT NOT NULL,
  doc_title TEXT NOT NULL,
  text TEXT NOT NULL,
  page_start INTEGER NOT NULL,
  page_end INTEGER NOT NULL,
  section TEXT NOT NULL,
  idx INTEGER NOT NULL,
  dim INTEGER NOT NULL,
  vec BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
"""


class VectorStore:
    def __init__(self, path: str | Path, embedder: Embedder):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._embedder = embedder
        self._lock = threading.Lock()
        self._ids: np.ndarray | None = None  # row ids aligned with _mat
        self._mat: np.ndarray | None = None  # (N, dim) float32, rows L2-normalised
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    # ---- writes -------------------------------------------------------------
    def add_chunks(self, chunks: list[Chunk], doc_title: str, batch: int = 32) -> None:
        t0 = time.time()
        for i in range(0, len(chunks), batch):
            part = chunks[i : i + batch]
            vecs = np.asarray(self._embedder.encode([c.text for c in part]), dtype=np.float32)
            rows = [
                (c.chunk_id, c.doc_id, doc_title, c.text,
                 -1 if c.page_start is None else c.page_start,
                 -1 if c.page_end is None else c.page_end,
                 c.section, c.index, int(v.shape[0]), v.tobytes())
                for c, v in zip(part, vecs)
            ]
            with self._conn() as c:
                c.executemany(
                    "INSERT INTO chunks(chunk_id,doc_id,doc_title,text,page_start,page_end,section,idx,dim,vec) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(chunk_id) DO UPDATE SET "
                    "doc_id=excluded.doc_id, doc_title=excluded.doc_title, text=excluded.text, "
                    "page_start=excluded.page_start, page_end=excluded.page_end, section=excluded.section, "
                    "idx=excluded.idx, dim=excluded.dim, vec=excluded.vec",
                    rows,
                )
            log.info("Embedded %d/%d chunks (%.0fs elapsed)", min(i + batch, len(chunks)), len(chunks),
                     time.time() - t0)
        self._invalidate()

    def delete_document(self, doc_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
        self._invalidate()

    def _invalidate(self) -> None:
        with self._lock:
            self._ids = self._mat = None

    # ---- reads --------------------------------------------------------------
    def count(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    def _matrix(self, dim: int) -> tuple[np.ndarray, np.ndarray]:
        """Vectors of the given dimension, cached until the next write."""
        with self._lock:
            if self._mat is not None and self._mat.shape[1] == dim:
                return self._ids, self._mat
            with self._conn() as c:
                n = c.execute("SELECT COUNT(*) FROM chunks WHERE dim=?", (dim,)).fetchone()[0]
                total = c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
                if total and n < total:
                    log.error("%d of %d stored chunks were embedded with a different model and are ignored. "
                              "Delete and re-upload those documents.", total - n, total)
                mat = np.empty((n, dim), dtype=np.float32)
                ids = np.empty(n, dtype=np.int64)
                for j, r in enumerate(c.execute("SELECT id, vec FROM chunks WHERE dim=? ORDER BY id", (dim,))):
                    ids[j] = r["id"]
                    mat[j] = np.frombuffer(r["vec"], dtype=np.float32)
            self._ids, self._mat = ids, mat
            return ids, mat

    def query(self, text: str, k: int) -> list[Hit]:
        if self.count() == 0:
            return []
        q = np.asarray(self._embedder.encode([text]), dtype=np.float32)[0]
        ids, mat = self._matrix(int(q.shape[0]))
        if len(ids) == 0:
            return []
        scores = mat @ q  # both sides are unit length -> cosine similarity
        k = min(k, len(ids))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        marks = ",".join("?" * len(top))
        with self._conn() as c:
            rows = {r["id"]: r for r in c.execute(
                f"SELECT * FROM chunks WHERE id IN ({marks})", [int(ids[i]) for i in top])}
        hits: list[Hit] = []
        for i in top:
            r = rows.get(int(ids[i]))
            if r is None:  # deleted between the cache read and the lookup
                continue
            ps, pe = r["page_start"], r["page_end"]
            hits.append(Hit(r["chunk_id"], r["doc_id"], r["doc_title"], r["text"],
                            None if ps < 0 else ps, None if pe < 0 else pe,
                            r["section"], float(scores[i])))
        return hits
