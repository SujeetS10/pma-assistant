from __future__ import annotations

import re
from typing import Literal

from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request,
                     UploadFile)
from pydantic import BaseModel, Field

from .. import security
from ..deps import get_svc, require_admin
from ..services import ingestion
from ..services.factory import Services

router = APIRouter()


@router.get("/stats")
def stats(_: str = Depends(require_admin), svc: Services = Depends(get_svc)):
    return svc.db.stats()


@router.get("/documents")
def documents(_: str = Depends(require_admin), svc: Services = Depends(get_svc)):
    return [{k: d[k] for k in ("id", "title", "kind", "filename", "status", "error", "pages",
                               "chunks", "size_bytes", "uploaded_by", "created_at")}
            for d in svc.db.doc_list()]


@router.post("/documents", status_code=202)
def upload(request: Request, bg: BackgroundTasks, file: UploadFile = File(...), title: str = Form(""),
           admin: str = Depends(require_admin), svc: Services = Depends(get_svc)):
    limit = svc.settings.max_upload_mb * 1024 * 1024
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit + 1_000_000:
        raise HTTPException(413, f"File too large (max {svc.settings.max_upload_mb} MB).")
    try:
        ext = ingestion.check_extension(file.filename or "")
    except ingestion.BadUpload as e:
        raise HTTPException(415, str(e))

    doc_id = ingestion.new_doc_id()
    path = svc.settings.upload_dir / f"{doc_id}{ext}"
    size = 0
    with path.open("wb") as out:
        while chunk := file.file.read(1 << 20):
            size += len(chunk)
            if size > limit:
                out.close()
                path.unlink(missing_ok=True)
                raise HTTPException(413, f"File too large (max {svc.settings.max_upload_mb} MB).")
            out.write(chunk)
    if size == 0:
        path.unlink(missing_ok=True)
        raise HTTPException(400, "The uploaded file is empty.")

    fname = re.sub(r"[^\w.\- ]", "_", file.filename or f"document{ext}")
    try:
        ingestion.register(svc, doc_id=doc_id, path=path, kind="file", filename=fname,
                           title=title.strip() or fname.rsplit(".", 1)[0], uploaded_by=admin)
    except ingestion.Duplicate as e:
        raise HTTPException(409, f"This exact file is already uploaded as '{e.title}'.")
    bg.add_task(ingestion.process_document, svc, doc_id)
    return {"id": doc_id, "status": "queued"}


class NoteIn(BaseModel):
    title: str = Field(max_length=200)
    text: str = Field(max_length=200_000)


@router.post("/notes", status_code=202)
def add_note(body: NoteIn, bg: BackgroundTasks, admin: str = Depends(require_admin),
             svc: Services = Depends(get_svc)):
    try:
        doc_id = ingestion.create_note(svc, body.title, body.text, admin)
    except ingestion.BadUpload as e:
        raise HTTPException(422, str(e))
    except ingestion.Duplicate as e:
        raise HTTPException(409, f"This exact note already exists as '{e.title}'.")
    bg.add_task(ingestion.process_document, svc, doc_id)
    return {"id": doc_id, "status": "queued"}


@router.delete("/documents/{doc_id}")
def delete_doc(doc_id: str, _: str = Depends(require_admin), svc: Services = Depends(get_svc)):
    try:
        if not ingestion.delete_document(svc, doc_id):
            raise HTTPException(404, "Document not found.")
    except ingestion.BadUpload as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


# ---- roster / access mode ---------------------------------------------------
class RosterIn(BaseModel):
    reg_nos: str = Field(max_length=200_000)


class ModeIn(BaseModel):
    roster_mode: Literal["open", "roster"]


@router.get("/roster")
def roster(_: str = Depends(require_admin), svc: Services = Depends(get_svc)):
    return {"mode": svc.db.get_setting("roster_mode", "open"), "reg_nos": svc.db.roster_list()}


@router.post("/roster")
def roster_add(body: RosterIn, _: str = Depends(require_admin), svc: Services = Depends(get_svc)):
    tokens = [t for t in re.split(r"[\s,;]+", body.reg_nos) if t]
    valid = [security.normalize_reg_no(t) for t in tokens]
    good = sorted({v for v in valid if v})
    added = svc.db.roster_add(good)
    return {"added": added, "invalid": sum(1 for v in valid if not v), "total": len(svc.db.roster_list())}


@router.delete("/roster/{reg_no}")
def roster_remove(reg_no: str, _: str = Depends(require_admin), svc: Services = Depends(get_svc)):
    svc.db.roster_remove(reg_no.strip().upper())
    return {"ok": True}


@router.put("/settings")
def set_mode(body: ModeIn, _: str = Depends(require_admin), svc: Services = Depends(get_svc)):
    if body.roster_mode == "roster" and not svc.db.roster_list():
        raise HTTPException(409, "Add at least one register number before restricting access.")
    svc.db.set_setting("roster_mode", body.roster_mode)
    return {"mode": body.roster_mode}
