from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
  id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, client_name TEXT NOT NULL,
  transcript TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, meeting_id INTEGER NOT NULL REFERENCES meetings(id),
  version INTEGER NOT NULL, kind TEXT NOT NULL,            -- initial | follow_up
  transcript TEXT NOT NULL, data TEXT NOT NULL,
  approved_by TEXT, approved_at TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(meeting_id, version)
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
