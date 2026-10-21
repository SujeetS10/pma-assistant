"""Document parsing with page metadata. Heavy libraries are imported lazily."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SUPPORTED = {".pdf", ".docx", ".txt", ".md"}


class ParseError(Exception):
    """Raised for unsupported, corrupt, encrypted or text-less files."""


@dataclass
class Page:
    page: int | None  # 1-based for PDFs; None when the format has no pages
    text: str


def parse_file(path: str | Path) -> list[Page]:
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in SUPPORTED:
        raise ParseError(f"Unsupported file type '{ext}'. Supported: {sorted(SUPPORTED)}")
    if not p.is_file():
        raise ParseError(f"File not found: {p}")
    if ext == ".pdf":
        return _parse_pdf(p)
    if ext == ".docx":
        return _parse_docx(p)
    return _parse_text(p)


def _parse_pdf(p: Path) -> list[Page]:
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise ParseError("PyMuPDF is not installed (pip install pymupdf).") from e
    try:
        doc = fitz.open(p)
    except Exception as e:
        raise ParseError(f"Could not open PDF: {e}") from e
    if doc.needs_pass:
        raise ParseError("PDF is encrypted; upload an unprotected copy.")
    pages = [Page(i + 1, doc[i].get_text("text").strip()) for i in range(len(doc))]
    if not any(pg.text for pg in pages):
        raise ParseError(
            "No extractable text (likely a scanned PDF). OCR it first, then re-upload."
        )
    empty = [pg.page for pg in pages if not pg.text]
    if empty:
        print(f"warning: no text on pages {empty} of {p.name} (images/scans?)")
    return [pg for pg in pages if pg.text]


def _parse_docx(p: Path) -> list[Page]:
    try:
        import docx
    except ImportError as e:
        raise ParseError("python-docx is not installed.") from e
    try:
        d = docx.Document(str(p))
    except Exception as e:
        raise ParseError(f"Could not open DOCX: {e}") from e
    parts: list[str] = []
    for para in d.paragraphs:
        t = para.text.strip()
        if not t:
            parts.append("")
        elif para.style is not None and para.style.name.lower().startswith("heading"):
            parts.append("# " + t)  # normalise so the chunker sees section headings
        else:
            parts.append(t)
    text = "\n".join(parts).strip()
    if not text:
        raise ParseError("DOCX contains no text.")
    return [Page(None, text)]


def _parse_text(p: Path) -> list[Page]:
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = p.read_text(encoding="latin-1")
    if not text.strip():
        raise ParseError("File is empty.")
    return [Page(None, text.strip())]
