"""Service container. Heavy parts (embedding model, Chroma, LLM client) are built lazily and once."""
from __future__ import annotations

import threading

from ..config import Settings
from ..db import Database
from ..rag.embedding import SentenceTransformerEmbedder
from ..rag.llm_client import LLMClient
from ..rag.rag import RagService
from ..rag.retrieval import Retriever
from ..rag.vector_store import ChromaStore


class Services:
    """Holds settings + DB + vector store + RAG. Tests may pass fakes for store/rag."""

    def __init__(self, settings: Settings, store=None, rag: RagService | None = None):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        self.db = Database(settings.db_path)
        self.ingest_lock = threading.Lock()  # serialise indexing: embeddings are CPU heavy
        self._init_lock = threading.Lock()
        self._store, self._rag = store, rag

    @property
    def store(self):
        with self._init_lock:
            if self._store is None:
                self._store = ChromaStore(
                    self.settings.chroma_path, SentenceTransformerEmbedder(self.settings.embedding_model))
            return self._store

    @property
    def rag(self) -> RagService:
        store = self.store
        with self._init_lock:
            if self._rag is None:
                s = self.settings
                self._rag = RagService(
                    Retriever(store, s.top_k, s.max_context_chunks, s.min_score),
                    LLMClient(s.llm_api_key, s.llm_model, s.llm_base_url),  # raises LLMError if key/model missing
                )
            return self._rag


# Used by evaluation/CLI scripts
def build_retriever(s: Settings) -> Retriever:
    store = ChromaStore(s.chroma_path, SentenceTransformerEmbedder(s.embedding_model))
    return Retriever(store, s.top_k, s.max_context_chunks, s.min_score)


def build_rag(s: Settings) -> RagService:
    return RagService(build_retriever(s), LLMClient(s.llm_api_key, s.llm_model, s.llm_base_url))
