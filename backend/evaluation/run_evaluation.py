"""Run retrieval (and optionally answer) evaluation.

  python evaluation/run_evaluation.py --dataset evaluation/dataset.example.jsonl --retrieval-only
  python evaluation/run_evaluation.py --dataset my_questions.jsonl          # needs LLM_API_KEY + LLM_MODEL

Dataset fields per line: id, question, answerable (bool), type, and any of
expected_doc, expected_pages, expected_keywords. Metrics only use fields you provide.
Outputs JSON + CSV into --out.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation import metrics as M  # noqa: E402
from app.config import Settings  # noqa: E402


def load(path: Path) -> list[dict]:
    items = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path}:{n}: invalid JSON ({e})")
    return items


def evaluate(items: list[dict], retriever, rag=None, ks=(1, 3, 5)) -> dict:
    rows = []
    for it in items:
        answerable = it.get("answerable", True)
        hits = retriever.retrieve(it["question"])
        flags = [M.is_relevant(h, it) for h in hits]
        has_gt = answerable and any(it.get(k) for k in ("expected_doc", "expected_pages", "expected_keywords"))
        rank = M.first_relevant_rank(flags) if has_gt else None
        row = {
            "id": it["id"], "type": it.get("type", ""), "answerable": answerable,
            "n_retrieved": len(hits), "rank_of_first_relevant": rank,
            "reciprocal_rank": M.reciprocal_rank(rank) if has_gt else None,
            **{f"hit@{k}": (M.hit_at_k(rank, k) if has_gt else None) for k in ks},
            # Retrieval-level abstention: nothing passed the relevance floor.
            "retrieval_abstained": len(hits) == 0,
        }
        if rag is not None:
            ans = rag.answer(it["question"])
            row.update({
                "answer_abstained": ans.abstained,
                "grounded": ans.grounded if not ans.abstained else None,
                "citation_validity": M.citation_validity(ans.text, len(ans.sources)),
                "invalid_markers": len(ans.invalid_markers),
                "keyword_coverage": M.keyword_coverage(ans.text, it.get("expected_keywords")) if answerable else None,
                "latency_ms": ans.latency_ms,
                "answer": ans.text,
            })
        rows.append(row)

    ans_rows = [r for r in rows if r["answerable"]]
    unans = [r for r in rows if not r["answerable"]]
    agg = {
        "n_questions": len(rows), "n_answerable": len(ans_rows), "n_unanswerable": len(unans),
        "retrieval": {
            f"hit@{k}": M.mean(r[f"hit@{k}"] for r in ans_rows) for k in ks
        } | {"mrr": M.mean(r["reciprocal_rank"] for r in ans_rows)},
        # Of out-of-scope questions, how many retrieved nothing above the relevance floor.
        "retrieval_abstention_rate_on_unanswerable": M.mean(
            1.0 if r["retrieval_abstained"] else 0.0 for r in unans),
    }
    if rag is not None:
        agg["answers"] = {
            "abstained_on_unanswerable": M.mean(1.0 if r["answer_abstained"] else 0.0 for r in unans),
            "false_abstention_on_answerable": M.mean(1.0 if r["answer_abstained"] else 0.0 for r in ans_rows),
            "grounded_rate": M.mean(
                (1.0 if r["grounded"] else 0.0) if r.get("grounded") is not None else None for r in rows),
            "citation_validity": M.mean(r["citation_validity"] for r in rows),
            "keyword_coverage": M.mean(r["keyword_coverage"] for r in ans_rows),
            "mean_latency_ms": M.mean(r["latency_ms"] for r in rows),
        }
    return {"rows": rows, "aggregate": agg}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("eval_out"))
    ap.add_argument("--retrieval-only", action="store_true")
    a = ap.parse_args()

    from app.services.factory import build_rag, build_retriever
    s = Settings.from_env()
    items = load(a.dataset)
    rag = None if a.retrieval_only else build_rag(s)
    retriever = rag.retriever if rag else build_retriever(s)
    result = evaluate(items, retriever, rag)
    result["config"] = {
        "dataset": str(a.dataset), "embedding_model": s.embedding_model, "top_k": s.top_k,
        "max_context_chunks": s.max_context_chunks, "min_score": s.min_score,
        "chunk_chars": s.chunk_chars, "llm_model": None if a.retrieval_only else s.llm_model,
        "run_at": datetime.now(timezone.utc).isoformat(),
    }
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    with (a.out / "results.csv").open("w", newline="", encoding="utf-8") as f:
        cols = sorted({k for r in result["rows"] for k in r})
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(result["rows"])
    print(json.dumps(result["aggregate"], indent=2))
    print(f"\nWrote {a.out/'results.json'} and {a.out/'results.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
