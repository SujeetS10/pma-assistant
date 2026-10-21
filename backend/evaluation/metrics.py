"""Pure metric functions. Missing ground truth is skipped (None), never guessed."""
from __future__ import annotations

import re
from typing import Iterable, Sequence

from app.rag.citations import extract


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def is_relevant(hit, item: dict) -> bool | None:
    """Does a retrieved hit satisfy the item's ground truth? None if no ground truth given."""
    exp_doc = item.get("expected_doc")
    pages = item.get("expected_pages")
    kws = item.get("expected_keywords")
    if not (exp_doc or pages or kws):
        return None
    if exp_doc and exp_doc not in (hit.doc_id, hit.doc_title):  # doc ids are random; titles are friendlier
        return False
    if pages:
        if hit.page_start is None:
            return False
        lo, hi = hit.page_start, hit.page_end or hit.page_start
        if not any(lo <= p <= hi for p in pages):
            return False
    if kws and not any(_norm(k) in _norm(hit.text) for k in kws):
        return False
    return True


def first_relevant_rank(flags: Sequence[bool | None]) -> int | None:
    for i, f in enumerate(flags, 1):
        if f:
            return i
    return None


def hit_at_k(rank: int | None, k: int) -> float:
    return 1.0 if rank is not None and rank <= k else 0.0


def reciprocal_rank(rank: int | None) -> float:
    return 1.0 / rank if rank else 0.0


def keyword_coverage(answer: str, keywords: Iterable[str] | None) -> float | None:
    kws = list(keywords or [])
    if not kws:
        return None
    a = _norm(answer)
    return sum(_norm(k) in a for k in kws) / len(kws)


def citation_validity(answer: str, n_sources: int) -> float | None:
    """Fraction of cited markers that point at a real supplied source (None if none cited)."""
    nums = extract(answer)
    if not nums:
        return None
    return sum(1 <= n <= n_sources for n in nums) / len(nums)


def mean(values: Iterable[float | None]) -> dict:
    """Mean over non-None values, reporting how many items contributed."""
    vals = [v for v in values if v is not None]
    return {"value": (sum(vals) / len(vals)) if vals else None, "n": len(vals)}
