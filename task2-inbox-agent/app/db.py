from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS emails (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_name TEXT, customer_email TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
  previous_conversation TEXT NOT NULL DEFAULT '[]',
  category TEXT, status TEXT NOT NULL DEFAULT 'new',   -- new | drafted | approved | rejected
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, email_id INTEGER NOT NULL REFERENCES emails(id),
  payload TEXT NOT NULL,                                -- full structured draft JSON
  body TEXT NOT NULL, category TEXT NOT NULL, mode TEXT NOT NULL, model TEXT, prompt_version TEXT NOT NULL,
  eligible INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT, email_id INTEGER NOT NULL, draft_id INTEGER,
  category TEXT NOT NULL, action TEXT NOT NULL,         -- approved_unchanged | approved_edited | replaced | rejected
  original_email TEXT NOT NULL, original_draft TEXT, final_text TEXT, diff TEXT,
  eligible INTEGER NOT NULL DEFAULT 0, model TEXT, prompt_version TEXT, mode TEXT,
  reviewer TEXT, reason TEXT, evaluation_outcome TEXT,  -- good | bad | NULL
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS category_stats (
  category TEXT PRIMARY KEY, streak INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'manual_only',
  revoked_reason TEXT, total_reviewed INTEGER NOT NULL DEFAULT 0, total_unchanged INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS outbound (
  id INTEGER PRIMARY KEY AUTOINCREMENT, email_id INTEGER NOT NULL, to_address TEXT NOT NULL, subject TEXT NOT NULL,
  body TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'SIMULATED_NOT_SENT', sent_by TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._mem = sqlite3.connect(":memory:", check_same_thread=False) if path == ":memory:" else None
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self):
        c = self._mem or sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            if not self._mem:
                c.close()

    def all(self, sql, args=()):
        with self.conn() as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        r = self.all(sql, args)
        return r[0] if r else None

    def run(self, sql, args=()):
        with self.conn() as c:
            return c.execute(sql, args).lastrowid
