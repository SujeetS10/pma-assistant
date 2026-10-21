"""Inspect retrieval from the terminal (no LLM key needed).

  cd backend && python -m scripts.ask "What is the memoryless property?"
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.services.factory import build_retriever  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    for i, h in enumerate(build_retriever(Settings.from_env()).retrieve(" ".join(sys.argv[1:])), 1):
        pg = "" if h.page_start is None else f" p.{h.page_start}"
        print(f"[S{i}] score={h.score:.3f} {h.doc_title}{pg} | {h.section}\n     {h.text[:200]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
