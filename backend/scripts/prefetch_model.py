"""Download the embedding model into MODEL_CACHE_DIR. Run at BUILD time so the server never has to download it
(on hosts with an ephemeral disk, like Render free, that would otherwise happen on every cold start).

  cd backend && python -m scripts.prefetch_model
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.rag.embedding import FastEmbedEmbedder  # noqa: E402


def main() -> int:
    s = Settings.from_env()
    if s.embedding_provider != "local":
        print("EMBEDDING_PROVIDER is not 'local'; nothing to download.")
        return 0
    s.model_cache_dir.mkdir(parents=True, exist_ok=True)
    emb = FastEmbedEmbedder(s.embedding_model, s.model_cache_dir)
    dim = emb.encode(["warm-up"]).shape[1]
    print(f"Model '{s.embedding_model}' cached in {s.model_cache_dir} (dim={dim}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
