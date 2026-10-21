from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import chat_limiter, get_svc, require_student
from ..rag.llm_client import LLMError
from ..services import chat_service
from ..services.factory import Services

log = logging.getLogger("pma.student")
router = APIRouter()


class ChatIn(BaseModel):
    conversation_id: int | None = None
    message: str = Field(max_length=chat_service.MAX_QUESTION_CHARS + 500)


@router.get("/conversations")
def conversations(reg: str = Depends(require_student), svc: Services = Depends(get_svc)):
    return svc.db.conv_list(reg)


@router.get("/conversations/{conv_id}")
def conversation(conv_id: int, reg: str = Depends(require_student), svc: Services = Depends(get_svc)):
    if not svc.db.conv_owned(reg, conv_id):
        raise HTTPException(404, "Conversation not found.")
    return {"id": conv_id, "messages": svc.db.msg_list(reg, conv_id)}


@router.delete("/conversations/{conv_id}")
def delete_conversation(conv_id: int, reg: str = Depends(require_student), svc: Services = Depends(get_svc)):
    if not svc.db.conv_delete(reg, conv_id):
        raise HTTPException(404, "Conversation not found.")
    return {"ok": True}


@router.get("/library")
def library(_: str = Depends(require_student), svc: Services = Depends(get_svc)):
    """Titles of the material the assistant currently answers from."""
    return [{"id": d["id"], "title": d["title"], "kind": d["kind"], "pages": d["pages"]}
            for d in svc.db.doc_list(ready_only=True)]


@router.post("/chat")
def chat(body: ChatIn, reg: str = Depends(require_student), svc: Services = Depends(get_svc)):
    if not chat_limiter.allow(reg):
        raise HTTPException(429, "You're asking too fast. Wait a few seconds.")
    try:
        r = chat_service.handle_chat(svc, reg, body.conversation_id, body.message)
    except chat_service.BadQuestion as e:
        raise HTTPException(422, str(e))
    except chat_service.NotFound as e:
        raise HTTPException(404, str(e))
    except LLMError as e:
        log.warning("LLM error: %s", e)
        raise HTTPException(502, f"The AI service is unavailable: {e}")
    return {"conversation_id": r.conversation_id, "message_id": r.assistant_message_id,
            "answer": r.answer, "sources": r.sources, "abstained": r.abstained,
            "grounded": r.grounded, "latency_ms": r.latency_ms}
