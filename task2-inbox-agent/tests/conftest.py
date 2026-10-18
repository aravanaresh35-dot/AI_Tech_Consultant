import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "task2-inbox-agent"))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from tech_common.kb_client import KnowledgeBrainClient  # noqa: E402

PASSAGE = {"title": "How to enable the member login page", "url": "https://demo.example/kb/member-login.html",
           "snippet": "Open Settings...", "text": "T\nOpen Settings, then Members, then Login Page, and switch on Enable Login Page. "
                                                   "Enable features in settings under the Settings menu."}


class KBState:
    mode = "supported"  # supported | insufficient | down


@pytest.fixture()
def kb_state():
    return KBState()


@pytest.fixture()
def kb(kb_state):
    def handler(req: httpx.Request):
        if kb_state.mode == "down":
            raise httpx.ConnectError("refused")
        if req.url.path == "/api/v1/search":
            if kb_state.mode == "insufficient":
                return httpx.Response(200, json={"evidence_status": "insufficient", "confidence": 0.0, "passages": []})
            return httpx.Response(200, json={"evidence_status": "supported", "confidence": 1.0, "passages": [PASSAGE]})
        return httpx.Response(200, json={"status": "ok", "ai": {"mode": "demo"}, "articles_active": 16})
    return KnowledgeBrainClient("http://kb.test", transport=httpx.MockTransport(handler), retries=0)


@pytest.fixture()
def make_client(kb, tmp_path):
    def _make(db=":memory:", ai=None, **kw):
        s = Settings(db_path=db)
        for k, v in kw.items():
            setattr(s, k, v)
        return TestClient(create_app(s, kb=kb, ai=ai))
    return _make


@pytest.fixture()
def client(make_client):
    return make_client()


def new_email(c, subject="Enable login", body="How do I enable the member login page?", name="Ana Ruiz", addr="ana@x.example"):
    r = c.post("/api/v1/emails", json={"customer_name": name, "customer_email": addr, "subject": subject, "body": body})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def drafted(c, **kw):
    eid = new_email(c, **kw)
    return eid, c.post(f"/api/v1/emails/{eid}/draft").json()
