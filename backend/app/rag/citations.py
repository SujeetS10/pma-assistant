"""Parsing and validation of [S#] citation markers in model output."""
from __future__ import annotations

import re

_GROUP = re.compile(r"\[(\s*S\d+(?:\s*[,;]\s*S\d+)*\s*)\]")
_NUM = re.compile(r"S(\d+)")


def normalize(text: str) -> str:
    """Rewrite [S1, S2] as [S1][S2] so every marker is a single [S#]."""
    return _GROUP.sub(lambda m: "".join(f"[S{n}]" for n in _NUM.findall(m.group(1))), text)


def extract(text: str) -> list[int]:
    """Ordered, de-duplicated citation numbers appearing in the text."""
    seen: list[int] = []
    for n in _NUM.findall(" ".join(m.group(1) for m in _GROUP.finditer(normalize(text)))):
        if int(n) not in seen:
            seen.append(int(n))
    return seen


def validate(text: str, n_sources: int) -> tuple[str, list[int], list[int]]:
    """Return (cleaned_text, valid_numbers, invalid_numbers).

    Markers pointing at sources that were never supplied are removed from the text.
    """
    text = normalize(text)
    nums = extract(text)
    valid = [n for n in nums if 1 <= n <= n_sources]
    invalid = [n for n in nums if n not in valid]
    for n in invalid:
        text = re.sub(rf"\s*\[S{n}\]", "", text)
    return text, valid, invalid
