"""Embeddings, built to fit small servers (e.g. Render free, 512 MB RAM).

Default: the SAME model as before (all-MiniLM-L6-v2) but run through ONNX Runtime via `fastembed`,
so PyTorch is not needed (saves ~500 MB+). The model loads lazily on first use.

Optional: EMBEDDING_PROVIDER=api uses any OpenAI-compatible /embeddings endpoint, which needs almost no
local memory. Vectors from different models are not comparable, so re-upload documents after switching.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np


class Embedder(Protocol):
    def encode(self, texts: list[str]) -> "np.ndarray | list[list[float]]": ...


def _normalize(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float32)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.maximum(norms, 1e-12)


class FastEmbedEmbedder:
    """Local ONNX embedder. Small batches and a single thread keep peak memory low."""

    def __init__(self, model_name: str, cache_dir: str | Path | None = None,
                 threads: int = 1, batch_size: int = 16):
        self.model_name = model_name
        self.cache_dir = str(cache_dir) if cache_dir else None
        self.threads, self.batch_size = threads, batch_size
        self._model = None

    def _load(self):
        if self._model is None:
            from fastembed import TextEmbedding  # downloads the model on first run if not cached

            self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir,
                                        threads=self.threads)
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        vecs = list(self._load().embed(texts, batch_size=self.batch_size))
        return _normalize(np.vstack(vecs))


class ApiEmbedder:
    """OpenAI-compatible embeddings endpoint (no local model, minimal RAM)."""

    def __init__(self, api_key: str, model: str, base_url: str, batch_size: int = 64):
        if not api_key or not model:
            raise ValueError("EMBEDDING_API_KEY and EMBEDDING_MODEL must be set for EMBEDDING_PROVIDER=api.")
        from openai import OpenAI

        self.model, self.batch_size = model, batch_size
        self._client = OpenAI(api_key=api_key, base_url=base_url or None, timeout=60.0, max_retries=2)

    def encode(self, texts: list[str]) -> np.ndarray:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            r = self._client.embeddings.create(model=self.model, input=texts[i : i + self.batch_size])
            out.extend(d.embedding for d in sorted(r.data, key=lambda d: d.index))
        return _normalize(np.array(out, dtype=np.float32))


def make_embedder(settings) -> Embedder:
    if settings.embedding_provider == "api":
        return ApiEmbedder(settings.embedding_api_key, settings.embedding_model, settings.embedding_base_url)
    return FastEmbedEmbedder(settings.embedding_model, settings.model_cache_dir)
