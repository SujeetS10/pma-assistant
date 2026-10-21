"""One chat turn: answer from the shared knowledge base and persist it under the student's register number."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..rag.rag import Answer
from .factory import Services

MAX_QUESTION_CHARS = 2000
_MARKER = re.compile(r"\s*\[S\d+\]")


class NotFound(Exception):
    pass


class BadQuestion(Exception):
    pass


@dataclass
class ChatResult:
    conversation_id: int
    user_message_id: int
    assistant_message_id: int
    answer: str
    sources: list[dict]
    abstained: bool
    grounded: bool
    latency_ms: int


def _source_dicts(ans: Answer) -> list[dict]:
    """Only sources the answer actually cited, keyed by their [S#] number."""
    out = []
    for n in ans.cited:
        h = ans.sources[n - 1]
        out.append({"n": n, "doc_id": h.doc_id, "doc_title": h.doc_title, "page_start": h.page_start,
                    "page_end": h.page_end, "section": h.section, "snippet": h.text[:500],
                    "score": round(h.score, 3)})
    return out


def handle_chat(svc: Services, reg_no: str, conversation_id: int | None, message: str) -> ChatResult:
    message = (message or "").strip()
    if not message:
        raise BadQuestion("Type a question first.")
    if len(message) > MAX_QUESTION_CHARS:
        raise BadQuestion(f"Question is too long (max {MAX_QUESTION_CHARS} characters).")

    history: list[dict] = []
    if conversation_id is not None:
        if not svc.db.conv_owned(reg_no, conversation_id):  # ownership comes from the session, never the client
            raise NotFound("Conversation not found.")
        for m in svc.db.msg_list(reg_no, conversation_id)[-6:]:
            text = _MARKER.sub("", m["content"]) if m["role"] == "assistant" else m["content"]
            history.append({"role": m["role"], "content": text})

    ans = svc.rag.answer(message, history)  # may raise LLMError; nothing is saved in that case

    if conversation_id is None:
        conversation_id = svc.db.conv_create(reg_no, message)
    uid = svc.db.msg_add(conversation_id, "user", message)
    sources = _source_dicts(ans)
    aid = svc.db.msg_add(conversation_id, "assistant", ans.text, sources, ans.abstained, ans.grounded)
    return ChatResult(conversation_id, uid, aid, ans.text, sources, ans.abstained, ans.grounded, ans.latency_ms)
