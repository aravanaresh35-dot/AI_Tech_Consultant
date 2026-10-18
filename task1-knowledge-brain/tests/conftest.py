import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "task1-knowledge-brain"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

DEMO = ROOT / "task1-knowledge-brain" / "data" / "demo_site"


class FakeLiveAI:
    """TEST DOUBLE ONLY. Pretends to be a live model so we can test the live code path offline."""
    is_live, mode, model = True, "live", "test-double"

    def __init__(self, answer="Test double answer.", supported=True, fail=False):
        self.answer, self.supported, self.fail = answer, supported, fail

    def generate_json(self, system, user, schema, version, max_tokens=0):
        from tech_common.ai import AIUnavailable
        if self.fail:
            raise AIUnavailable("down")
        return schema(answer=self.answer, supported=self.supported), None

    def generate(self, *a, **k):
        from tech_common.ai import AIUnavailable
        raise AIUnavailable("vision unavailable")


@pytest.fixture()
def site(tmp_path):
    dst = tmp_path / "site"
    shutil.copytree(DEMO, dst)
    return dst


@pytest.fixture()
def make_client(tmp_path, site):
    def _make(db=":memory:", **kw):
        s = Settings(db_path=db, demo_site_dir=str(site), crawl_source="demo")
        for k, v in kw.items():
            setattr(s, k, v)
        return TestClient(create_app(s, ai=kw.get("_ai") if "_ai" in kw else None))
    return _make


@pytest.fixture()
def client(make_client):
    return make_client()


@pytest.fixture()
def loaded(client):
    client.post("/api/v1/ingest")
    return client
