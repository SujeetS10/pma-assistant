"""Retrieval with a relevance floor (so unrelated questions abstain) and de-duplication."""
from __future__ import annotations

from typing import Protocol

from .vector_store import Hit


class Searchable(Protocol):
    def query(self, text: str, k: int) -> list[Hit]: ...


class Retriever:
    def __init__(self, store: Searchable, top_k: int = 8, max_context: int = 5,
                 min_score: float = 0.30):
        self.store, self.top_k = store, top_k
        self.max_context, self.min_score = max_context, min_score

    def retrieve(self, question: str) -> list[Hit]:
        """Return up to max_context hits scoring >= min_score, best first."""
        raw = sorted(self.store.query(question, self.top_k), key=lambda h: -h.score)
        out: list[Hit] = []
        seen: set[str] = set()
        for h in raw:
            key = " ".join(h.text.split())[:200].lower()
            if h.score < self.min_score or key in seen:
                continue
            seen.add(key)
            out.append(h)
            if len(out) == self.max_context:
                break
        return out
