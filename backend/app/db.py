"""SQLite persistence (stdlib). One short-lived connection per operation; WAL mode.

Everything here lives in DATA_DIR/app.db so it survives restarts and is shared by all logins.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS admins (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS students (
  reg_no TEXT PRIMARY KEY,
  created_at REAL NOT NULL,
  last_login REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS roster (
  reg_no TEXT PRIMARY KEY,
  added_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  role TEXT NOT NULL CHECK (role IN ('admin','student')),
  subject TEXT NOT NULL,
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('file','note')),
  filename TEXT NOT NULL,
  sha256 TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL CHECK (status IN ('queued','processing','ready','failed')),
  error TEXT NOT NULL DEFAULT '',
  pages INTEGER NOT NULL DEFAULT 0,
  chunks INTEGER NOT NULL DEFAULT 0,
  size_bytes INTEGER NOT NULL DEFAULT 0,
  uploaded_by TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reg_no TEXT NOT NULL REFERENCES students(reg_no) ON DELETE CASCADE,
  title TEXT NOT NULL,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_reg ON conversations(reg_no, updated_at DESC);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user','assistant')),
  content TEXT NOT NULL,
  sources_json TEXT NOT NULL DEFAULT '[]',
  abstained INTEGER NOT NULL DEFAULT 0,
  grounded INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, id);
"""


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA journal_mode=WAL")
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    # ---- admins -------------------------------------------------------
    def admin_count(self) -> int:
        with self.conn() as c:
            return c.execute("SELECT COUNT(*) FROM admins").fetchone()[0]

    def upsert_admin(self, username: str, password_hash: str) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO admins(username,password_hash,created_at) VALUES(?,?,?) "
                "ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash",
                (username, password_hash, time.time()),
            )

    def get_admin(self, username: str):
        with self.conn() as c:
            return c.execute("SELECT * FROM admins WHERE username=?", (username,)).fetchone()

    # ---- sessions -----------------------------------------------------
    def create_session(self, token_hash: str, role: str, subject: str, ttl_s: float) -> None:
        now = time.time()
        with self.conn() as c:
            c.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            c.execute("INSERT INTO sessions VALUES(?,?,?,?,?)", (token_hash, role, subject, now, now + ttl_s))

    def get_session(self, token_hash: str):
        with self.conn() as c:
            return c.execute(
                "SELECT role, subject FROM sessions WHERE token_hash=? AND expires_at>?",
                (token_hash, time.time()),
            ).fetchone()

    def delete_session(self, token_hash: str) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))

    # ---- settings / roster / students ----------------------------------
    def get_setting(self, key: str, default: str) -> str:
        with self.conn() as c:
            r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def set_setting(self, key: str, value: str) -> None:
        with self.conn() as c:
            c.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      (key, value))

    def roster_add(self, reg_nos: list[str]) -> int:
        with self.conn() as c:
            before = c.execute("SELECT COUNT(*) FROM roster").fetchone()[0]
            c.executemany("INSERT OR IGNORE INTO roster VALUES(?,?)", [(r, time.time()) for r in reg_nos])
            return c.execute("SELECT COUNT(*) FROM roster").fetchone()[0] - before

    def roster_remove(self, reg_no: str) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM roster WHERE reg_no=?", (reg_no,))

    def roster_list(self) -> list[str]:
        with self.conn() as c:
            return [r["reg_no"] for r in c.execute("SELECT reg_no FROM roster ORDER BY reg_no")]

    def roster_has(self, reg_no: str) -> bool:
        with self.conn() as c:
            return c.execute("SELECT 1 FROM roster WHERE reg_no=?", (reg_no,)).fetchone() is not None

    def touch_student(self, reg_no: str) -> None:
        now = time.time()
        with self.conn() as c:
            c.execute(
                "INSERT INTO students VALUES(?,?,?) ON CONFLICT(reg_no) DO UPDATE SET last_login=excluded.last_login",
                (reg_no, now, now),
            )

    # ---- documents ----------------------------------------------------
    def doc_by_sha(self, sha: str):
        with self.conn() as c:
            return c.execute("SELECT * FROM documents WHERE sha256=?", (sha,)).fetchone()

    def doc_add(self, **f) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO documents(id,title,kind,filename,sha256,status,size_bytes,uploaded_by,created_at) "
                "VALUES(:id,:title,:kind,:filename,:sha256,'queued',:size_bytes,:uploaded_by,:created_at)",
                {**f, "created_at": time.time()},
            )

    def doc_update(self, doc_id: str, **f) -> None:
        cols = ", ".join(f"{k}=?" for k in f)
        with self.conn() as c:
            c.execute(f"UPDATE documents SET {cols} WHERE id=?", (*f.values(), doc_id))

    def doc_get(self, doc_id: str):
        with self.conn() as c:
            return c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()

    def doc_list(self, ready_only: bool = False) -> list[dict]:
        q = "SELECT * FROM documents" + (" WHERE status='ready'" if ready_only else "") + " ORDER BY created_at DESC"
        with self.conn() as c:
            return [dict(r) for r in c.execute(q)]

    def doc_delete(self, doc_id: str) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM documents WHERE id=?", (doc_id,))

    def fail_interrupted_docs(self) -> int:
        """Documents left 'queued/processing' by a crash/restart can never finish; mark them failed."""
        with self.conn() as c:
            cur = c.execute(
                "UPDATE documents SET status='failed', error='Interrupted by a server restart; delete and re-upload.' "
                "WHERE status IN ('queued','processing')")
            return cur.rowcount

    # ---- conversations / messages (always scoped by reg_no) -------------
    def conv_create(self, reg_no: str, title: str) -> int:
        now = time.time()
        with self.conn() as c:
            return c.execute("INSERT INTO conversations(reg_no,title,created_at,updated_at) VALUES(?,?,?,?)",
                             (reg_no, title[:80], now, now)).lastrowid

    def conv_list(self, reg_no: str) -> list[dict]:
        with self.conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT id,title,created_at,updated_at FROM conversations WHERE reg_no=? ORDER BY updated_at DESC",
                (reg_no,))]

    def conv_owned(self, reg_no: str, conv_id: int) -> bool:
        with self.conn() as c:
            return c.execute("SELECT 1 FROM conversations WHERE id=? AND reg_no=?", (conv_id, reg_no)).fetchone() is not None

    def conv_delete(self, reg_no: str, conv_id: int) -> bool:
        with self.conn() as c:
            return c.execute("DELETE FROM conversations WHERE id=? AND reg_no=?", (conv_id, reg_no)).rowcount > 0

    def msg_add(self, conv_id: int, role: str, content: str, sources: list[dict] | None = None,
                abstained: bool = False, grounded: bool = False) -> int:
        now = time.time()
        with self.conn() as c:
            mid = c.execute(
                "INSERT INTO messages(conversation_id,role,content,sources_json,abstained,grounded,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (conv_id, role, content, json.dumps(sources or []), int(abstained), int(grounded), now)).lastrowid
            c.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conv_id))
            return mid

    def msg_list(self, reg_no: str, conv_id: int) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT m.* FROM messages m JOIN conversations v ON v.id=m.conversation_id "
                "WHERE m.conversation_id=? AND v.reg_no=? ORDER BY m.id", (conv_id, reg_no)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["sources"] = json.loads(d.pop("sources_json"))
            d["abstained"], d["grounded"] = bool(d["abstained"]), bool(d["grounded"])
            out.append(d)
        return out

    def stats(self) -> dict:
        with self.conn() as c:
            one = lambda q: c.execute(q).fetchone()[0]
            return {
                "documents_ready": one("SELECT COUNT(*) FROM documents WHERE status='ready'"),
                "documents_total": one("SELECT COUNT(*) FROM documents"),
                "students": one("SELECT COUNT(*) FROM students"),
                "conversations": one("SELECT COUNT(*) FROM conversations"),
                "questions_asked": one("SELECT COUNT(*) FROM messages WHERE role='user'"),
            }
