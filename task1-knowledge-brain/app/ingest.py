"""Ingestion and daily sync.

ingest(): process sitemap URLs that are not yet 'done' (resumable; progress saved per URL).
sync():   diff sitemap vs stored articles -> add new, refetch changed, deactivate removed.
Both are idempotent: running them twice produces no extra changes.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from tech_common.ai import AIClient
from tech_common.logging_setup import log

from .config import Settings
from .db import Database
from .extract import extract_article, is_article_url, parse_sitemap
from .fetcher import FetchError, Fetcher
from .images import process_images
from .store import ArticleStore

logger = logging.getLogger("ingest")
MAX_SITEMAP_DEPTH = 3


class Ingestor:
    def __init__(self, db: Database, store: ArticleStore, fetcher: Fetcher, ai: AIClient, settings: Settings):
        self.db, self.store, self.fetcher, self.ai, self.s = db, store, fetcher, ai, settings

    # ---- discovery -------------------------------------------------------------------------
    def discover(self) -> list[dict]:
        """Fetch the sitemap (and child sitemaps), return unique article entries."""
        seen_maps: set[str] = set()
        found: dict[str, dict] = {}

        def walk(url: str, depth: int):
            if url in seen_maps or depth > MAX_SITEMAP_DEPTH:
                return
            seen_maps.add(url)
            urls, children = parse_sitemap(self.fetcher.get_text(url))
            for u in urls:
                if is_article_url(u["url"]):
                    found.setdefault(u["url"], u)
            for child in children:
                walk(child, depth + 1)

        walk(self.s.sitemap_url, 0)
        return list(found.values())

    # ---- single page -----------------------------------------------------------------------
    def _process(self, entry: dict) -> str:
        url = entry["url"]
        attempts_row = self.db.one("SELECT attempts FROM ingest_progress WHERE url=?", (url,))
        attempts = (attempts_row["attempts"] if attempts_row else 0) + 1
        try:
            html = self.fetcher.get_text(url)
            art = extract_article(html, url)
            imgs = process_images(art.images, self.fetcher, self.ai, self.s.analyze_images, self.s.max_image_bytes)
            content = art.content
            extra = [f"Image: {(i.get('alt') or '').strip()} {(i.get('caption') or '').strip()} "
                     f"{(i.get('analysis') or '').strip()}".strip() for i in imgs
                     if (i.get("alt") or i.get("caption") or i.get("analysis"))]
            if extra:
                content = content + "\n" + "\n".join(extra)
            result = self.store.upsert(url=url, title=art.title, content=content, headings=art.headings,
                                       images=imgs, lastmod=entry.get("lastmod"))
            self.db.run("""INSERT INTO ingest_progress(url,status,attempts,error,updated_at) VALUES(?,?,?,NULL,datetime('now'))
                           ON CONFLICT(url) DO UPDATE SET status='done',attempts=?,error=NULL,updated_at=datetime('now')""",
                        (url, "done", attempts, attempts))
            return result
        except (FetchError, ValueError) as exc:  # one bad page must not stop the run
            self.db.run("""INSERT INTO ingest_progress(url,status,attempts,error,updated_at) VALUES(?,?,?,?,datetime('now'))
                           ON CONFLICT(url) DO UPDATE SET status='failed',attempts=?,error=?,updated_at=datetime('now')""",
                        (url, "failed", attempts, str(exc)[:300], attempts, str(exc)[:300]))
            log(logger, "page_failed", url=url, error=str(exc)[:200])
            return "failed"

    # ---- public operations -----------------------------------------------------------------
    def ingest(self, max_pages: Optional[int] = None, retry_failed: bool = True) -> dict:
        run_id = self.db.run("INSERT INTO runs(kind) VALUES('ingest')")
        report = {"added": 0, "updated": 0, "unchanged": 0, "failed": 0, "skipped_done": 0,
                  "remaining": 0, "batches": 0}
        entries = self.discover()
        done = {r["url"] for r in self.db.all("SELECT url FROM ingest_progress WHERE status='done'")}
        failed = {r["url"] for r in self.db.all("SELECT url FROM ingest_progress WHERE status='failed'")}
        todo = []
        for e in entries:
            if e["url"] in done:
                report["skipped_done"] += 1
            elif e["url"] in failed and not retry_failed:
                continue
            else:
                todo.append(e)
        limit = min(max_pages or self.s.max_pages, self.s.max_pages)
        batch = todo[:limit]
        report["remaining"] = max(0, len(todo) - len(batch))
        for i in range(0, len(batch), self.s.batch_size):
            report["batches"] += 1
            for e in batch[i:i + self.s.batch_size]:
                report[self._process(e)] += 1
        return self._finish(run_id, report)

    def sync(self) -> dict:
        run_id = self.db.run("INSERT INTO runs(kind) VALUES('sync')")
        report = {"added": 0, "updated": 0, "unchanged": 0, "removed": 0, "failed": 0, "skipped_lastmod": 0}
        entries = self.discover()
        current = {e["url"] for e in entries}
        for e in entries:
            existing = self.store.get_by_url(e["url"])
            if existing and existing["active"] == 1 and e.get("lastmod") and existing["lastmod"] == e["lastmod"]:
                report["skipped_lastmod"] += 1  # unchanged lastmod -> do not refetch
                continue
            report[self._process(e)] += 1
        for url in self.store.active_urls("crawl") - current:
            self.store.deactivate(url)
            report["removed"] += 1
        return self._finish(run_id, report)

    def _finish(self, run_id: int, report: dict) -> dict:
        self.db.run("UPDATE runs SET finished_at=datetime('now'), report=? WHERE id=?", (json.dumps(report), run_id))
        log(logger, "run_finished", run_id=run_id, **report)
        return report

    def status(self) -> dict:
        last = self.db.all("SELECT kind, started_at, finished_at, report FROM runs ORDER BY id DESC LIMIT 5")
        for r in last:
            r["report"] = json.loads(r["report"]) if r["report"] else None
        counts = self.db.one("""SELECT SUM(active=1) active, SUM(active=0) inactive, COUNT(*) total FROM articles""")
        failed = self.db.all("SELECT url, attempts, error FROM ingest_progress WHERE status='failed'")
        return {"articles": {k: (v or 0) for k, v in counts.items()}, "failed_pages": failed, "recent_runs": last}
