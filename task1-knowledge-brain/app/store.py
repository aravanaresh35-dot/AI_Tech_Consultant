"""Article persistence: upsert with content hashes, chunking, soft-delete."""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from .db import Database
from .retrieval import chunk_text


def content_hash(title: str, content: str) -> str:
    return hashlib.sha256(f"{title}\n{content}".encode()).hexdigest()


class ArticleStore:
    def __init__(self, db: Database):
        self.db = db

    def get_by_url(self, url: str) -> Optional[dict]:
        return self.db.one("SELECT * FROM articles WHERE url=?", (url,))

    def upsert(self, *, url: str, title: str, content: str, headings: list[str], images: list[dict],
               lastmod: Optional[str] = None, source: str = "crawl") -> str:
        """Returns 'added' | 'updated' | 'unchanged'. Safe to call repeatedly (idempotent)."""
        h = content_hash(title, content)
        existing = self.get_by_url(url)
        if existing and existing["content_hash"] == h and existing["active"] == 1:
            if lastmod and existing["lastmod"] != lastmod:
                self.db.run("UPDATE articles SET lastmod=? WHERE id=?", (lastmod, existing["id"]))
            return "unchanged"
        with self.db.conn() as c:
            if existing:
                aid = existing["id"]
                c.execute("""UPDATE articles SET title=?, content=?, headings=?, content_hash=?, lastmod=?,
                             active=1, updated_at=datetime('now') WHERE id=?""",
                          (title, content, json.dumps(headings), h, lastmod, aid))
                c.execute("DELETE FROM chunks WHERE article_id=?", (aid,))
                c.execute("DELETE FROM images WHERE article_id=?", (aid,))
                result = "updated"
            else:
                aid = c.execute(
                    "INSERT INTO articles(url,title,content,headings,content_hash,source,lastmod) VALUES(?,?,?,?,?,?,?)",
                    (url, title, content, json.dumps(headings), h, source, lastmod)).lastrowid
                result = "added"
            for i, ch in enumerate(chunk_text(title, content)):
                c.execute("INSERT INTO chunks(article_id,idx,text) VALUES(?,?,?)", (aid, i, ch))
            for im in images:
                c.execute("""INSERT INTO images(article_id,url,alt,caption,analysis,analysis_status,analysis_note)
                             VALUES(?,?,?,?,?,?,?)""",
                          (aid, im["url"], im.get("alt"), im.get("caption"), im.get("analysis"),
                           im.get("analysis_status", "not_analyzed"), im.get("analysis_note")))
        return result

    def deactivate(self, url: str) -> bool:
        cur = self.db.run("UPDATE articles SET active=0, updated_at=datetime('now') WHERE url=? AND active=1", (url,))
        return bool(self.db.one("SELECT 1 x FROM articles WHERE url=? AND active=0", (url,)))

    def active_urls(self, source: str = "crawl") -> set[str]:
        return {r["url"] for r in self.db.all("SELECT url FROM articles WHERE active=1 AND source=?", (source,))}
