"""Bulk-add files from the command line. They are registered in the same database and vector store the
web app uses, so they appear in the admin dashboard.

  cd backend && python -m scripts.ingest_cli path/to/lecture1.pdf path/to/notes.docx
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.services import ingestion  # noqa: E402
from app.services.factory import Services  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    a = ap.parse_args()
    svc = Services(Settings.from_env())
    rc = 0
    for f in a.files:
        try:
            ext = ingestion.check_extension(f.name)
            doc_id = ingestion.new_doc_id()
            dest = svc.settings.upload_dir / f"{doc_id}{ext}"
            shutil.copyfile(f, dest)
            ingestion.register(svc, doc_id=doc_id, path=dest, title=f.stem, kind="file",
                               filename=f.name, uploaded_by="cli")
        except (ingestion.BadUpload, ingestion.Duplicate, OSError) as e:
            print(f"SKIPPED {f}: {e}", file=sys.stderr)
            rc = 1
            continue
        ingestion.process_document(svc, doc_id)
        row = svc.db.doc_get(doc_id)
        print(f"{row['status'].upper():7} {f.name}  chunks={row['chunks']}  {row['error']}")
        rc = rc or (row["status"] != "ready")
    return int(rc)


if __name__ == "__main__":
    raise SystemExit(main())
