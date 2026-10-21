"""ChromaDB persistence and semantic search (cosine similarity)."""
from __future__ import annotations

from dataclasses import dataclass

from .chunking import Chunk
from .embedding import Embedder


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


class ChromaStore:
    def __init__(self, path: str, embedder: Embedder, collection: str = "pma_chunks"):
        import chromadb

        self._client = chromadb.PersistentClient(path=path)
        self._col = self._client.get_or_create_collection(
            collection, metadata={"hnsw:space": "cosine"}
        )
        self._embedder = embedder

    def add_chunks(self, chunks: list[Chunk], doc_title: str, batch: int = 64) -> None:
        for i in range(0, len(chunks), batch):
            part = chunks[i : i + batch]
            self._col.upsert(
                ids=[c.chunk_id for c in part],
                documents=[c.text for c in part],
                embeddings=self._embedder.encode([c.text for c in part]),
                metadatas=[
                    {
                        "doc_id": c.doc_id,
                        "doc_title": doc_title,
                        "page_start": -1 if c.page_start is None else c.page_start,
                        "page_end": -1 if c.page_end is None else c.page_end,
                        "section": c.section,
                        "index": c.index,
                    }
                    for c in part
                ],
            )

    def delete_document(self, doc_id: str) -> None:
        self._col.delete(where={"doc_id": doc_id})

    def count(self) -> int:
        return self._col.count()

    def query(self, text: str, k: int) -> list[Hit]:
        if self._col.count() == 0:
            return []
        res = self._col.query(
            query_embeddings=self._embedder.encode([text]),
            n_results=min(k, self._col.count()),
        )
        hits: list[Hit] = []
        for cid, doc, meta, dist in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            ps, pe = meta["page_start"], meta["page_end"]
            hits.append(
                Hit(
                    chunk_id=cid,
                    doc_id=meta["doc_id"],
                    doc_title=meta["doc_title"],
                    text=doc,
                    page_start=None if ps < 0 else ps,
                    page_end=None if pe < 0 else pe,
                    section=meta["section"],
                    score=1.0 - float(dist),
                )
            )
        return hits
