"""Inbox Agent API (Task 2). Python was used (permitted fallback) instead of TypeScript; see DESIGN.md."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from tech_common.ai import AIClient
from tech_common.kb_client import KnowledgeBrainClient, KnowledgeBrainUnavailable
from tech_common.logging_setup import setup_logging

from .automation import AutomationTracker
from .config import Settings
from .db import Database
from .drafting import DraftingService
from .service import InboxService

logger = logging.getLogger("inbox.api")
EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def _nonblank(v: str) -> str:
    if not v.strip():
        raise ValueError("must not be blank")
    return v.strip()


class Message(BaseModel):
    from_: str = Field(alias="from", max_length=50)
    text: str = Field(max_length=4000)


class EmailIn(BaseModel):
    customer_name: Optional[str] = Field(default="", max_length=120)
    customer_email: str = Field(pattern=EMAIL_RE, max_length=254)
    subject: str = Field(max_length=300)
    body: str = Field(max_length=8000)
    previous_conversation: list[dict] = Field(default_factory=list, max_length=30)
    _s = field_validator("subject", "body")(_nonblank)


class ReviewIn(BaseModel):
    final_text: Optional[str] = Field(default=None, max_length=8000)
    reviewer: str = Field(default="reviewer", max_length=100)
    category: Optional[str] = None
    reason: Optional[str] = Field(default=None, max_length=1000)


class OutcomeIn(BaseModel):
    outcome: str = Field(pattern="^(good|bad)$")
    note: Optional[str] = Field(default=None, max_length=1000)


class EvalIn(BaseModel):
    category: str
    passed: bool
    note: str = Field(default="", max_length=500)


def create_app(settings: Optional[Settings] = None, kb: Optional[KnowledgeBrainClient] = None,
               ai: Optional[AIClient] = None) -> FastAPI:
    setup_logging()
    s = settings or Settings()
    db = Database(s.db_path)
    kb = kb or KnowledgeBrainClient()
    ai = ai or AIClient()
    tracker = AutomationTracker(db, s.auto_send_threshold)
    svc = InboxService(db, DraftingService(db, kb, ai, s), tracker, s)
    app = FastAPI(title="Inbox Agent", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.svc = svc

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        logger.exception("unhandled error")
        return JSONResponse(status_code=500, content={"detail": "Internal error. See server logs."})

    def need(eid: int) -> dict:
        e = svc.get_email(eid)
        if not e:
            raise HTTPException(404, "Email not found")
        return e

    @app.get("/health")
    def health():
        try:
            kb_state = {"status": "ok", **{k: v for k, v in kb.health().items() if k in ("ai", "articles_active")}}
        except KnowledgeBrainUnavailable as exc:
            kb_state = {"status": "unavailable", "detail": str(exc)}
        return {"status": "ok", "service": "inbox-agent", "ai": {"mode": ai.mode, "model": ai.model if ai.is_live else None},
                "knowledge_brain": kb_state, "auto_send_enabled": s.auto_send_enabled, "outbound_mode": "SIMULATED_NOT_SENT"}

    @app.post("/api/v1/emails", status_code=201)
    def create_email(e: EmailIn):
        return svc.create_email(e.customer_name, e.customer_email, e.subject, e.body, e.previous_conversation)

    @app.get("/api/v1/emails")
    def list_emails(status: Optional[str] = Query(None, pattern="^(new|drafted|approved|rejected)$")):
        return {"items": svc.list_emails(status)}

    @app.get("/api/v1/emails/{email_id}")
    def get_email(email_id: int):
        return need(email_id)

    def guarded(fn, *a):
        try:
            return fn(*a)
        except KeyError:
            raise HTTPException(404, "Email not found")
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @app.post("/api/v1/emails/{email_id}/draft")
    def draft(email_id: int):
        return guarded(svc.draft, email_id)

    @app.post("/api/v1/emails/{email_id}/approve")
    def approve(email_id: int, r: ReviewIn = ReviewIn()):
        return guarded(svc.review, email_id, "approve", r.final_text, r.reviewer, r.category, r.reason)

    @app.post("/api/v1/emails/{email_id}/replace")
    def replace(email_id: int, r: ReviewIn):
        if not (r.final_text or "").strip():
            raise HTTPException(422, "final_text is required for a human replacement")
        return guarded(svc.review, email_id, "replace", r.final_text, r.reviewer, r.category, r.reason)

    @app.post("/api/v1/emails/{email_id}/reject")
    def reject(email_id: int, r: ReviewIn = ReviewIn()):
        return guarded(svc.review, email_id, "reject", None, r.reviewer, r.category, r.reason)

    @app.post("/api/v1/emails/{email_id}/feedback")
    def feedback(email_id: int, o: OutcomeIn):
        return guarded(svc.record_outcome, email_id, o.outcome, o.note)

    @app.get("/api/v1/emails/{email_id}/feedback")
    def email_feedback(email_id: int):
        return {"items": need(email_id)["feedback"]}

    @app.get("/api/v1/feedback")
    def history(limit: int = Query(100, ge=1, le=500)):
        return {"items": svc.history(limit)}

    @app.get("/api/v1/automation-status")
    def automation_status():
        return {"threshold": s.auto_send_threshold, "auto_send_enabled": s.auto_send_enabled,
                "categories": tracker.status(), "metrics": svc.metrics()}

    @app.post("/api/v1/automation/evaluations")
    def evaluation(e: EvalIn):
        return guarded(svc.record_evaluation, e.category, e.passed, e.note)

    @app.get("/api/v1/outbound")
    def outbound():
        return {"mode": "SIMULATED_NOT_SENT", "items": svc.outbound()}

    return app


def get_app() -> FastAPI:
    return create_app()
