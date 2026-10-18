"""Meeting-to-SOW API (Task 3)."""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from tech_common.ai import AIClient
from tech_common.kb_client import KnowledgeBrainClient, KnowledgeBrainUnavailable
from tech_common.logging_setup import setup_logging

from .config import Settings
from .db import Database
from .pipeline import Pipeline

logger = logging.getLogger("sow.api")


class MeetingIn(BaseModel):
    title: str = Field(max_length=200)
    client_name: str = Field(max_length=200)
    transcript: str = Field(default="")
    _t = field_validator("title", "client_name")(lambda v: v.strip() or (_ for _ in ()).throw(ValueError("must not be blank")))


class FollowUpIn(BaseModel):
    transcript: str = Field(default="")


class ApproveIn(BaseModel):
    approver: str = Field(min_length=1, max_length=100)
    version: Optional[int] = Field(default=None, ge=1)


def create_app(settings: Optional[Settings] = None, kb: Optional[KnowledgeBrainClient] = None,
               ai: Optional[AIClient] = None) -> FastAPI:
    setup_logging()
    s = settings or Settings()
    db = Database(s.db_path)
    kb = kb or KnowledgeBrainClient()
    ai = ai or AIClient()
    pipe = Pipeline(ai, kb, s)
    app = FastAPI(title="Meeting to Scope of Work", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        logger.exception("unhandled error")
        return JSONResponse(status_code=500, content={"detail": "Internal error. See server logs."})

    def meeting_or_404(mid: int) -> dict:
        m = db.one("SELECT * FROM meetings WHERE id=?", (mid,))
        if not m:
            raise HTTPException(404, "Meeting not found")
        return m

    def versions(mid: int) -> list[dict]:
        rows = db.all("SELECT * FROM versions WHERE meeting_id=? ORDER BY version", (mid,))
        for r in rows:
            r["data"] = json.loads(r["data"])
        return rows

    def pick(mid: int, version: Optional[int]) -> dict:
        meeting_or_404(mid)
        vs = versions(mid)
        if not vs:
            raise HTTPException(409, "Meeting has not been analyzed yet. POST /analyze first.")
        if version is None:
            return vs[-1]
        for v in vs:
            if v["version"] == version:
                return v
        raise HTTPException(404, "Version not found")

    def check_transcript(t: str):
        if len(t) > s.max_transcript_chars:
            raise HTTPException(413, f"Transcript exceeds {s.max_transcript_chars} characters.")

    def save(mid: int, version: int, kind: str, transcript: str, bundle: dict) -> dict:
        db.run("INSERT INTO versions(meeting_id,version,kind,transcript,data) VALUES(?,?,?,?,?)",
               (mid, version, kind, transcript, json.dumps(bundle)))
        return {"meeting_id": mid, "version": version, "kind": kind, "validation": bundle["validation"],
                "total_hours": bundle["estimate"]["total_hours"], "meta": bundle["meta"], "approved": False}

    @app.get("/health")
    def health():
        try:
            kb_state = {"status": "ok", **{k: v for k, v in kb.health().items() if k in ("ai", "articles_active")}}
        except KnowledgeBrainUnavailable as exc:
            kb_state = {"status": "unavailable", "detail": str(exc)}
        return {"status": "ok", "service": "meeting-to-sow", "ai": {"mode": ai.mode, "model": ai.model if ai.is_live else None},
                "knowledge_brain": kb_state, "pricing": "configured" if s.hourly_rate else "not_configured",
                "schema_version": "sow-v1"}

    @app.post("/api/v1/meetings", status_code=201)
    def create_meeting(m: MeetingIn):
        check_transcript(m.transcript)
        mid = db.run("INSERT INTO meetings(title,client_name,transcript) VALUES(?,?,?)", (m.title, m.client_name, m.transcript))
        return {"id": mid, "title": m.title, "client_name": m.client_name, "transcript_chars": len(m.transcript)}

    @app.get("/api/v1/meetings")
    def list_meetings():
        rows = db.all("""SELECT m.id,m.title,m.client_name,m.created_at,
                         (SELECT MAX(version) FROM versions v WHERE v.meeting_id=m.id) latest_version,
                         (SELECT COUNT(*) FROM versions v WHERE v.meeting_id=m.id AND v.approved_by IS NOT NULL) approved_versions
                         FROM meetings m ORDER BY m.id DESC""")
        return {"items": rows}

    @app.get("/api/v1/meetings/{mid}")
    def get_meeting(mid: int):
        m = meeting_or_404(mid)
        return {**{k: m[k] for k in ("id", "title", "client_name", "created_at")},
                "versions": [{"version": v["version"], "kind": v["kind"], "approved_by": v["approved_by"],
                              "total_hours": v["data"]["estimate"]["total_hours"], "valid": v["data"]["validation"]["passed"],
                              "created_at": v["created_at"]} for v in versions(mid)]}

    @app.post("/api/v1/meetings/{mid}/analyze")
    def analyze(mid: int):
        m = meeting_or_404(mid)
        if versions(mid):
            raise HTTPException(409, "Already analyzed. Use /follow-up to create a new version.")
        if not m["transcript"].strip():
            raise HTTPException(422, "Transcript is empty.")
        bundle = pipe.run(m["client_name"], m["transcript"], 1)
        return save(mid, 1, "initial", m["transcript"], bundle)

    @app.post("/api/v1/meetings/{mid}/follow-up")
    def follow_up(mid: int, body: FollowUpIn):
        meeting_or_404(mid)
        check_transcript(body.transcript)
        if not body.transcript.strip():
            raise HTTPException(422, "Follow-up transcript is empty.")
        vs = versions(mid)
        if not vs:
            raise HTTPException(409, "Analyze the first meeting before adding a follow-up.")
        prev = vs[-1]  # previous version is preserved untouched; a NEW version is created
        m = meeting_or_404(mid)
        bundle = pipe.run(m["client_name"], body.transcript, prev["version"] + 1, prev["data"])
        return save(mid, prev["version"] + 1, "follow_up", body.transcript, bundle)

    @app.get("/api/v1/meetings/{mid}/versions")
    def list_versions(mid: int):
        meeting_or_404(mid)
        return {"items": [{"version": v["version"], "kind": v["kind"], "approved_by": v["approved_by"],
                           "approved_at": v["approved_at"], "created_at": v["created_at"]} for v in versions(mid)]}

    @app.get("/api/v1/meetings/{mid}/scope")
    def scope(mid: int, version: Optional[int] = Query(None, ge=1)):
        v = pick(mid, version)
        d = v["data"]
        return {"version": v["version"], "scope": d["scope"], "analysis": d["analysis"], "product_findings": d["findings"],
                "validation": d["validation"], "meta": d["meta"]}

    @app.get("/api/v1/meetings/{mid}/estimate")
    def estimate(mid: int, version: Optional[int] = Query(None, ge=1)):
        v = pick(mid, version)
        return {"version": v["version"], "estimate": v["data"]["estimate"], "meta": v["data"]["meta"]}

    @app.get("/api/v1/meetings/{mid}/proposal")
    def proposal(mid: int, version: Optional[int] = Query(None, ge=1)):
        v = pick(mid, version)
        p = v["data"]["proposal"]
        if v["approved_by"]:
            p["approval"] = {**p["approval"], "status": f"APPROVED by {v['approved_by']} (internal approval; NOT sent to client)",
                             "approved_at": v["approved_at"]}
        return {"version": v["version"], "approved": bool(v["approved_by"]), "proposal": p,
                "validation": v["data"]["validation"], "meta": v["data"]["meta"]}

    @app.get("/api/v1/meetings/{mid}/comparison")
    def comparison(mid: int, version: Optional[int] = Query(None, ge=1)):
        v = pick(mid, version)
        if not v["data"]["comparison"]:
            raise HTTPException(404, "This version has no comparison (it is the first version).")
        return {"version": v["version"], "comparison": v["data"]["comparison"]}

    @app.post("/api/v1/meetings/{mid}/approve")
    def approve(mid: int, body: ApproveIn):
        v = pick(mid, body.version)
        if v["approved_by"]:
            raise HTTPException(409, "This version is already approved.")
        if not v["data"]["validation"]["passed"]:
            raise HTTPException(409, "Validation has errors; fix the transcript/scope before approval.")
        db.run("UPDATE versions SET approved_by=?, approved_at=datetime('now') WHERE meeting_id=? AND version=?",
               (body.approver, mid, v["version"]))
        logger.info("version approved", extra={"fields": {"meeting_id": mid, "version": v["version"]}})
        return {"meeting_id": mid, "version": v["version"], "approved_by": body.approver, "dispatched_to_client": False,
                "note": "Approval is internal only. The system never sends proposals to clients."}

    return app


def get_app() -> FastAPI:
    return create_app()
