import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "task3-meeting-to-sow"))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from tech_common.kb_client import KnowledgeBrainClient  # noqa: E402

TRANSCRIPTS = ROOT / "task3-meeting-to-sow" / "sample_transcripts"
PASSAGE = {"title": "Map view settings", "url": "https://demo.example/kb/map-view.html",
           "snippet": "Enable Map View under Settings > Search.", "text": "Enable Map View under Settings > Search."}


def transcript(name: str) -> str:
    return (TRANSCRIPTS / name).read_text()


class KBState:
    """mode: 'map' = evidence only for map/notification topics; 'none' = never; 'all' = always; 'down' = unreachable."""
    mode = "map"
    queries: list


@pytest.fixture()
def kb_state():
    s = KBState()
    s.queries = []
    return s


@pytest.fixture()
def kb(kb_state):
    def handler(req: httpx.Request):
        if kb_state.mode == "down":
            raise httpx.ConnectError("refused")
        if req.url.path == "/api/v1/search":
            import json
            q = json.loads(req.content)["query"].lower()
            kb_state.queries.append(q)
            hit = kb_state.mode == "all" or (kb_state.mode == "map" and "map" in q)
            if hit:
                return httpx.Response(200, json={"evidence_status": "supported", "confidence": 0.9, "passages": [PASSAGE]})
            return httpx.Response(200, json={"evidence_status": "insufficient", "confidence": 0.0, "passages": []})
        return httpx.Response(200, json={"status": "ok", "ai": {"mode": "demo"}, "articles_active": 16})
    return KnowledgeBrainClient("http://kb.test", transport=httpx.MockTransport(handler), retries=0)


@pytest.fixture()
def make_client(kb):
    def _make(db=":memory:", **kw):
        s = Settings(db_path=db)
        for k, v in kw.items():
            setattr(s, k, v)
        return TestClient(create_app(s, kb=kb))
    return _make


@pytest.fixture()
def client(make_client):
    return make_client()


def analyzed(c, name="01_website_improvement.txt", client_name="Harbor Bikes"):
    mid = c.post("/api/v1/meetings", json={"title": "Kickoff", "client_name": client_name, "transcript": transcript(name)}).json()["id"]
    r = c.post(f"/api/v1/meetings/{mid}/analyze")
    assert r.status_code == 200, r.text
    return mid
