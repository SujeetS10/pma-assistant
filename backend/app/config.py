"""Settings from environment / .env. All persistent state lives under DATA_DIR."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
    except ImportError:
        pass


@dataclass(frozen=True)
class Settings:
    llm_api_key: str
    llm_model: str
    llm_base_url: str
    embedding_model: str
    data_dir: Path
    top_k: int
    max_context_chunks: int
    min_score: float
    chunk_chars: int
    admin_username: str
    admin_password: str
    session_hours: int
    cookie_secure: bool
    max_upload_mb: int
    # Memory-related options (defaults suit small hosts such as Render free).
    embedding_provider: str = "local"  # "local" (ONNX, no PyTorch) or "api" (OpenAI-compatible /embeddings)
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    model_cache_dir: Path = REPO_ROOT / ".model_cache"

    @property
    def vector_db_path(self) -> Path:
        return self.data_dir / "vectors.db"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()
        g = os.environ.get
        # Provider settings. Default is Groq; any OpenAI-compatible API works via LLM_BASE_URL.
        key = g("LLM_API_KEY") or g("GROQ_API_KEY") or ""
        model = g("LLM_MODEL") or g("GROQ_MODEL") or ""
        base = g("LLM_BASE_URL") or ""
        if not key and g("XAI_API_KEY"):  # legacy xAI configuration
            key, model = g("XAI_API_KEY", ""), model or g("GROK_MODEL", "")
            # Old variable names may hold a Groq key (they start with gsk_); route those to Groq.
            base = base or ("https://api.groq.com/openai/v1" if key.startswith("gsk_") else "https://api.x.ai/v1")
        base = base or "https://api.groq.com/openai/v1"
        return cls(
            llm_api_key=key,
            llm_model=model,
            llm_base_url=base,
            embedding_model=g("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
            data_dir=Path(g("DATA_DIR", str(REPO_ROOT / "data"))).resolve(),
            top_k=int(g("TOP_K", "8")),
            max_context_chunks=int(g("MAX_CONTEXT_CHUNKS", "5")),
            min_score=float(g("MIN_SCORE", "0.30")),
            chunk_chars=int(g("CHUNK_CHARS", "1200")),
            admin_username=g("ADMIN_USERNAME", ""),
            admin_password=g("ADMIN_PASSWORD", ""),
            session_hours=int(g("SESSION_HOURS", "12")),
            cookie_secure=g("COOKIE_SECURE", "false").lower() == "true",
            max_upload_mb=int(g("MAX_UPLOAD_MB", "20")),
            embedding_provider=g("EMBEDDING_PROVIDER", "local").strip().lower(),
            embedding_api_key=g("EMBEDDING_API_KEY", ""),
            embedding_base_url=g("EMBEDDING_BASE_URL", ""),
            model_cache_dir=Path(g("MODEL_CACHE_DIR", str(REPO_ROOT / ".model_cache"))).resolve(),
        )
