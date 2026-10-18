"""Knowledge Brain API (Task 1)."""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from tech_common.ai import AIClient
from tech_common.logging_setup import log, setup_logging

from .config import Settings
from .db import Database
from .fetcher import HttpFetcher, LocalFetcher
from .ingest import Ingestor
from .retrieval import Retriever
from .service import KnowledgeService
from .store import ArticleStore

logger = logging.getLogger("kb.api")


class _Text(BaseModel):
    @staticmethod
    def _clean(v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class ChatRequest(_Text):
    question: str = Field(max_length=2000)
    conversation_id: Optional[str] = Field(default=None, max_length=100)
    _v = field_validator("question")(_Text._clean)


class SearchRequest(_Text):
    query: str = Field(max_length=2000)
    top_k: int = Field(default=4, ge=1, le=10)
    _v = field_validator("query")(_Text._clean)


class IngestRequest(BaseModel):
    max_pages: Optional[int] = Field(default=None, ge=1, le=5000)
    retry_failed: bool = True


class TaskCreate(_Text):
    question: str = Field(max_length=2000)
    context: str = Field(default="", max_length=4000)
    _v = field_validator("question")(_Text._clean)


class TaskAnswer(_Text):
    answer: str = Field(max_length=6000)
    expert_name: str = Field(default="expert", max_length=100)
    _v = field_validator("answer")(_Text._clean)


def create_app(settings: Optional[Settings] = None, fetcher=None, ai: Optional[AIClient] = None) -> FastAPI:
    setup_logging()
    s = settings or Settings()
    db = Database(s.db_path)
    store = ArticleStore(db)
    ai = ai or AIClient()
    if fetcher is None:
        fetcher = LocalFetcher(s.demo_site_dir) if s.crawl_source == "demo" else HttpFetcher(
            s.user_agent, s.http_timeout, s.http_retries, s.request_delay)
    if s.crawl_source == "demo" and isinstance(fetcher, LocalFetcher):
        s.sitemap_url = f"{LocalFetcher.HOST}/sitemap.xml"
    ingestor = Ingestor(db, store, fetcher, ai, s)
    service = KnowledgeService(db, store, Retriever(db), ai, s)
    scheduler = {"enabled": False, "next_run": None}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        sched = None
        if s.sync_schedule_enabled:
            from apscheduler.schedulers.background import BackgroundScheduler
            sched = BackgroundScheduler(timezone="UTC")
            job = sched.add_job(ingestor.sync, "cron", hour=s.sync_hour_utc, minute=0, id="daily-sync")
            sched.start()
            scheduler["enabled"] = True
            scheduler["next_run"] = str(job.next_run_time)
            log(logger, "scheduler_started", hour_utc=s.sync_hour_utc)
        yield
        if sched:
            sched.shutdown(wait=False)

    app = FastAPI(title="Knowledge Brain", version="1.0.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.ingestor, app.state.service, app.state.db, app.state.settings = ingestor, service, db, s

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        logger.exception("unhandled error")
        return JSONResponse(status_code=500, content={"detail": "Internal error. See server logs."})

    @app.get("/health")
    def health():
        n = db.one("SELECT SUM(active=1) a, COUNT(*) t FROM articles")
        return {"status": "ok", "service": "knowledge-brain", "ai": {"mode": ai.mode, "model": ai.model if ai.is_live else None},
                "crawl_source": s.crawl_source, "articles_active": n["a"] or 0, "articles_total": n["t"] or 0,
                "scheduler": scheduler, "retrieval": "bm25 (no embeddings configured)"}

    @app.get("/api/v1/articles")
    def list_articles(active: Optional[bool] = None, q: Optional[str] = Query(None, max_length=200),
                      limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        where, args = [], []
        if active is not None:
            where.append("active=?"); args.append(1 if active else 0)
        if q:
            where.append("(title LIKE ? OR content LIKE ?)"); args += [f"%{q}%", f"%{q}%"]
        w = ("WHERE " + " AND ".join(where)) if where else ""
        rows = db.all(f"SELECT id,url,title,source,active,lastmod,updated_at,substr(content,1,200) preview "
                      f"FROM articles {w} ORDER BY id LIMIT ? OFFSET ?", tuple(args) + (limit, offset))
        total = db.one(f"SELECT COUNT(*) n FROM articles {w}", tuple(args))["n"]
        return {"total": total, "items": rows}

    @app.get("/api/v1/articles/{article_id}")
    def get_article(article_id: int):
        a = db.one("SELECT * FROM articles WHERE id=?", (article_id,))
        if not a:
            raise HTTPException(404, "Article not found")
        a["headings"] = json.loads(a["headings"])
        a["images"] = db.all("SELECT url,alt,caption,analysis,analysis_status,analysis_note FROM images WHERE article_id=?", (article_id,))
        return a

    @app.post("/api/v1/ingest")
    def ingest(req: IngestRequest = IngestRequest()):
        try:
            return ingestor.ingest(req.max_pages, req.retry_failed)
        except Exception as exc:
            logger.warning("ingest failed: %s", type(exc).__name__)
            raise HTTPException(502, f"Could not read the sitemap: {str(exc)[:200]}")

    @app.post("/api/v1/sync")
    def sync():
        try:
            return ingestor.sync()
        except Exception as exc:
            logger.warning("sync failed: %s", type(exc).__name__)
            raise HTTPException(502, f"Could not read the sitemap: {str(exc)[:200]}")

    @app.get("/api/v1/ingest/status")
    def ingest_status():
        return ingestor.status()

    @app.post("/api/v1/search")
    def search(req: SearchRequest):
        return service.search(req.query, req.top_k)

    @app.post("/api/v1/chat")
    def chat(req: ChatRequest):
        return service.chat(req.question, req.conversation_id)

    @app.post("/api/v1/tasks", status_code=201)
    def create_task(req: TaskCreate):
        return service.create_task(req.question, req.context)

    @app.get("/api/v1/tasks")
    def tasks(status: Optional[str] = Query(None, pattern="^(pending|answered)$")):
        return {"items": service.list_tasks(status)}

    @app.post("/api/v1/tasks/{task_id}/answer")
    def answer_task(task_id: int, req: TaskAnswer):
        try:
            return service.answer_task(task_id, req.answer, req.expert_name)
        except KeyError:
            raise HTTPException(404, "Task not found")
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    return app


def get_app() -> FastAPI:  # uvicorn --factory app.main:get_app
    return create_app()
