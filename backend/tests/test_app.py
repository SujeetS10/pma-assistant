"""Offline tests for persistence, auth, isolation, ingestion lifecycle and chat flow (stdlib only).

Run from backend/:  python -m unittest discover -s tests -v
"""
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import security
from app.config import Settings
from app.db import Database
from app.rag.llm_client import LLMError
from app.rag.rag import Answer
from app.rag.vector_store import Hit
from app.services import auth_service, chat_service, ingestion
from app.services.factory import Services


def make_settings(data_dir: Path, **kw) -> Settings:
    base = dict(llm_api_key="k", llm_model="m", llm_base_url="https://example.test/v1", embedding_model="x", data_dir=data_dir, top_k=8,
                max_context_chunks=5, min_score=0.3, chunk_chars=400, admin_username="", admin_password="",
                session_hours=1, cookie_secure=False, max_upload_mb=5)
    base.update(kw)
    return Settings(**base)


class FakeStore:
    def __init__(self):
        self.docs = {}

    def add_chunks(self, chunks, title):
        self.docs[chunks[0].doc_id] = (title, len(chunks))

    def delete_document(self, doc_id):
        self.docs.pop(doc_id, None)


class FakeRag:
    def __init__(self, answer=None, error=None):
        self.answer_obj, self.error, self.calls = answer, error, []

    def answer(self, question, history=None):
        self.calls.append((question, history))
        if self.error:
            raise self.error
        return self.answer_obj


def grounded_answer():
    h = Hit("c1", "doc1", "Lecture 3", "The mean of a geometric variable is 1/p. " * 20, 4, 5, "Geometric", 0.82)
    return Answer("The mean is $1/p$ [S1].", [h], cited=[1], grounded=True, latency_ms=12, model="fake")


class SecurityTests(unittest.TestCase):
    def test_password_hash_roundtrip(self):
        h = security.hash_password("correct horse battery")
        self.assertTrue(security.verify_password("correct horse battery", h))
        self.assertFalse(security.verify_password("wrong", h))
        self.assertNotEqual(h, security.hash_password("correct horse battery"))  # salted
        self.assertFalse(security.verify_password("x", "garbage"))

    def test_reg_no_normalisation(self):
        self.assertEqual(security.normalize_reg_no(" 21bce1234 "), "21BCE1234")
        for bad in ["", "abc", "a b c d", "<script>", "x" * 40, "../etc", None]:
            self.assertIsNone(security.normalize_reg_no(bad), bad)

    def test_rate_limiter(self):
        rl = security.RateLimiter(2, 10)
        self.assertTrue(rl.allow("a", now=0)); self.assertTrue(rl.allow("a", now=1))
        self.assertFalse(rl.allow("a", now=2)); self.assertTrue(rl.allow("b", now=2))
        self.assertTrue(rl.allow("a", now=11.5))  # window slid

    def test_password_policy(self):
        self.assertIsNotNone(security.password_problem("short"))
        self.assertIsNone(security.password_problem("a-long-enough-password"))


class PersistenceTests(unittest.TestCase):
    def test_history_survives_restart_and_is_shared_kb_constant(self):
        with tempfile.TemporaryDirectory() as d:
            s = make_settings(Path(d))
            svc1 = Services(s, store=FakeStore(), rag=FakeRag(grounded_answer()))
            svc1.db.touch_student("21BCE0001")
            chat_service.handle_chat(svc1, "21BCE0001", None, "What is the mean?")
            note_id = ingestion.create_note(svc1, "Notes", "Some notes that are long enough to index.", "admin")
            ingestion.process_document(svc1, note_id)

            svc2 = Services(s, store=FakeStore(), rag=FakeRag(grounded_answer()))  # "restart"
            convs = svc2.db.conv_list("21BCE0001")
            self.assertEqual(len(convs), 1)
            msgs = svc2.db.msg_list("21BCE0001", convs[0]["id"])
            self.assertEqual([m["role"] for m in msgs], ["user", "assistant"])
            self.assertEqual(msgs[1]["sources"][0]["doc_title"], "Lecture 3")
            self.assertEqual([x["id"] for x in svc2.db.doc_list(ready_only=True)], [note_id])

    def test_isolation_between_students(self):
        with tempfile.TemporaryDirectory() as d:
            svc = Services(make_settings(Path(d)), store=FakeStore(), rag=FakeRag(grounded_answer()))
            for r in ("AAAA1111", "BBBB2222"):
                svc.db.touch_student(r)
            res = chat_service.handle_chat(svc, "AAAA1111", None, "private question")
            self.assertEqual(svc.db.conv_list("BBBB2222"), [])
            self.assertEqual(svc.db.msg_list("BBBB2222", res.conversation_id), [])
            self.assertFalse(svc.db.conv_delete("BBBB2222", res.conversation_id))
            with self.assertRaises(chat_service.NotFound):
                chat_service.handle_chat(svc, "BBBB2222", res.conversation_id, "hijack")
            self.assertEqual(len(svc.db.msg_list("AAAA1111", res.conversation_id)), 2)

    def test_sessions_expire_and_logout(self):
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "a.db")
            db.create_session("t1", "student", "X", ttl_s=60)
            db.create_session("t2", "student", "X", ttl_s=-1)
            self.assertIsNotNone(db.get_session("t1")); self.assertIsNone(db.get_session("t2"))
            db.delete_session("t1"); self.assertIsNone(db.get_session("t1"))

    def test_deleting_conversation_cascades_messages(self):
        with tempfile.TemporaryDirectory() as d:
            svc = Services(make_settings(Path(d)), store=FakeStore(), rag=FakeRag(grounded_answer()))
            svc.db.touch_student("AAAA1111")
            r = chat_service.handle_chat(svc, "AAAA1111", None, "q")
            self.assertTrue(svc.db.conv_delete("AAAA1111", r.conversation_id))
            with svc.db.conn() as c:
                self.assertEqual(c.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)


class AuthTests(unittest.TestCase):
    def test_student_open_and_roster_modes(self):
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "a.db")
            self.assertEqual(auth_service.student_login(db, " 21bce0001 "), "21BCE0001")
            with self.assertRaises(auth_service.AuthError):
                auth_service.student_login(db, "!!")
            db.roster_add(["21BCE0002"]); db.set_setting("roster_mode", "roster")
            self.assertEqual(auth_service.student_login(db, "21bce0002"), "21BCE0002")
            with self.assertRaises(auth_service.AuthError):
                auth_service.student_login(db, "21BCE0001")
            self.assertEqual(db.roster_add(["21BCE0002", "21BCE0003"]), 1)  # duplicates ignored

    def test_admin_login_and_bootstrap(self):
        with tempfile.TemporaryDirectory() as d:
            svc = Services(make_settings(Path(d), admin_username="prof", admin_password="a-long-password-1"),
                           store=FakeStore(), rag=FakeRag())
            auth_service.bootstrap_admin(svc.db, svc.settings)
            self.assertEqual(auth_service.admin_login(svc.db, "prof", "a-long-password-1"), "prof")
            for u, p in [("prof", "nope"), ("ghost", "a-long-password-1"), ("", "")]:
                with self.assertRaises(auth_service.AuthError):
                    auth_service.admin_login(svc.db, u, p)
            # editing the password in .env and restarting changes it
            s2 = make_settings(Path(d), admin_username="prof", admin_password="another-long-password")
            auth_service.bootstrap_admin(svc.db, s2)
            self.assertEqual(auth_service.admin_login(svc.db, "prof", "another-long-password"), "prof")

    def test_weak_admin_password_refused(self):
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "a.db")
            with self.assertRaises(SystemExit):
                auth_service.bootstrap_admin(db, make_settings(Path(d), admin_username="a", admin_password="short"))

    def test_session_token_only_stored_hashed(self):
        with tempfile.TemporaryDirectory() as d:
            svc = Services(make_settings(Path(d)), store=FakeStore(), rag=FakeRag())
            tok = auth_service.issue_session(svc.db, svc.settings, "student", "X")
            with svc.db.conn() as c:
                stored = c.execute("SELECT token_hash FROM sessions").fetchone()[0]
            self.assertNotEqual(stored, tok); self.assertEqual(stored, security.hash_token(tok))


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.store = FakeStore()
        self.svc = Services(make_settings(Path(self._d.name)), store=self.store, rag=FakeRag())

    def tearDown(self):
        self._d.cleanup()

    def test_note_lifecycle(self):
        doc_id = ingestion.create_note(self.svc, "Poisson", "Mean equals variance for a Poisson variable.", "admin")
        self.assertEqual(self.svc.db.doc_get(doc_id)["status"], "queued")
        ingestion.process_document(self.svc, doc_id)
        row = self.svc.db.doc_get(doc_id)
        self.assertEqual(row["status"], "ready"); self.assertGreaterEqual(row["chunks"], 1)
        self.assertIn(doc_id, self.store.docs)
        self.assertTrue(ingestion.delete_document(self.svc, doc_id))
        self.assertNotIn(doc_id, self.store.docs); self.assertIsNone(self.svc.db.doc_get(doc_id))
        self.assertEqual(list(self.svc.settings.upload_dir.glob(f"{doc_id}.*")), [])
        self.assertFalse(ingestion.delete_document(self.svc, doc_id))

    def test_duplicate_content_rejected(self):
        ingestion.create_note(self.svc, "A", "Identical body text for the duplicate check.", "admin")
        with self.assertRaises(ingestion.Duplicate):
            ingestion.create_note(self.svc, "A", "Identical body text for the duplicate check.", "admin")

    def test_unreadable_file_marked_failed_with_reason(self):
        doc_id = ingestion.new_doc_id()
        p = self.svc.settings.upload_dir / f"{doc_id}.txt"; p.write_text("   ")
        ingestion.register(self.svc, doc_id=doc_id, path=p, title="Blank", kind="file", filename="b.txt", uploaded_by="a")
        ingestion.process_document(self.svc, doc_id)
        row = self.svc.db.doc_get(doc_id)
        self.assertEqual(row["status"], "failed"); self.assertIn("empty", row["error"].lower())

    def test_extension_and_note_validation(self):
        with self.assertRaises(ingestion.BadUpload): ingestion.check_extension("virus.exe")
        self.assertEqual(ingestion.check_extension("Notes.PDF"), ".pdf")
        with self.assertRaises(ingestion.BadUpload): ingestion.create_note(self.svc, "", "x" * 50, "a")
        with self.assertRaises(ingestion.BadUpload): ingestion.create_note(self.svc, "T", "short", "a")

    def test_interrupted_documents_are_failed_on_restart(self):
        doc_id = ingestion.create_note(self.svc, "T", "Long enough note body for indexing.", "admin")
        self.svc.db.doc_update(doc_id, status="processing")
        self.assertEqual(self.svc.db.fail_interrupted_docs(), 1)
        self.assertEqual(self.svc.db.doc_get(doc_id)["status"], "failed")

    def test_cannot_delete_while_processing(self):
        doc_id = ingestion.create_note(self.svc, "T", "Long enough note body for indexing.", "admin")
        self.svc.db.doc_update(doc_id, status="processing")
        with self.assertRaises(ingestion.BadUpload): ingestion.delete_document(self.svc, doc_id)


class ChatFlowTests(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.rag = FakeRag(grounded_answer())
        self.svc = Services(make_settings(Path(self._d.name)), store=FakeStore(), rag=self.rag)
        self.svc.db.touch_student("21BCE0001")

    def tearDown(self):
        self._d.cleanup()

    def test_followup_uses_history_without_stale_markers(self):
        r1 = chat_service.handle_chat(self.svc, "21BCE0001", None, "What is the mean?")
        chat_service.handle_chat(self.svc, "21BCE0001", r1.conversation_id, "And the variance?")
        history = self.rag.calls[1][1]
        self.assertEqual([m["role"] for m in history], ["user", "assistant"])
        self.assertNotIn("[S1]", history[1]["content"])
        self.assertEqual(len(self.svc.db.msg_list("21BCE0001", r1.conversation_id)), 4)

    def test_sources_saved_with_snippet_capped(self):
        r = chat_service.handle_chat(self.svc, "21BCE0001", None, "q")
        s = r.sources[0]
        self.assertEqual((s["n"], s["doc_title"], s["page_start"], s["page_end"]), (1, "Lecture 3", 4, 5))
        self.assertLessEqual(len(s["snippet"]), 500)

    def test_abstention_persisted(self):
        self.rag.answer_obj = Answer("not covered", [], abstained=True)
        r = chat_service.handle_chat(self.svc, "21BCE0001", None, "Who won the World Cup?")
        m = self.svc.db.msg_list("21BCE0001", r.conversation_id)[1]
        self.assertTrue(m["abstained"]); self.assertEqual(m["sources"], [])

    def test_llm_failure_saves_nothing(self):
        self.rag.error = LLMError("down")
        with self.assertRaises(LLMError):
            chat_service.handle_chat(self.svc, "21BCE0001", None, "q")
        self.assertEqual(self.svc.db.conv_list("21BCE0001"), [])

    def test_input_validation(self):
        for bad in ["", "   ", "x" * 2001]:
            with self.assertRaises(chat_service.BadQuestion): chat_service.handle_chat(self.svc, "21BCE0001", None, bad)
        self.assertEqual(self.rag.calls, [])

    def test_title_from_first_question_truncated(self):
        r = chat_service.handle_chat(self.svc, "21BCE0001", None, "q" * 300)
        self.assertEqual(len(self.svc.db.conv_list("21BCE0001")[0]["title"]), 80)


if __name__ == "__main__":
    unittest.main()
