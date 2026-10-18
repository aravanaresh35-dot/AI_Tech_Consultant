"""HTTP client for the Knowledge Brain (Task 1). Tasks 2 and 3 use ONLY this to get facts."""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

import httpx

from .logging_setup import log

logger = logging.getLogger("kb_client")


class KnowledgeBrainUnavailable(RuntimeError):
    pass


class KnowledgeBrainClient:
    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None,
                 retries: Optional[int] = None, transport: Optional[httpx.BaseTransport] = None):
        self.base_url = (base_url or os.environ.get("KNOWLEDGE_BRAIN_URL", "http://localhost:8001")).rstrip("/")
        self.timeout = timeout if timeout is not None else float(os.environ.get("KB_TIMEOUT_SECONDS", "10"))
        self.retries = retries if retries is not None else int(os.environ.get("KB_RETRIES", "2"))
        self._http = httpx.Client(base_url=self.base_url, timeout=self.timeout, transport=transport)

    def _request(self, method: str, path: str, **kw) -> Any:
        last: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                r = self._http.request(method, path, **kw)
                if r.status_code >= 500:
                    raise httpx.HTTPStatusError("server error", request=r.request, response=r)
                if r.status_code >= 400:
                    raise KnowledgeBrainUnavailable(f"Knowledge Brain rejected request ({r.status_code}).")
                return r.json()
            except KnowledgeBrainUnavailable:
                raise
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last = exc
                log(logger, "kb_retry", path=path, attempt=attempt + 1, error=type(exc).__name__)
                if attempt < self.retries:
                    time.sleep(min(0.2 * 2**attempt, 2.0))
        raise KnowledgeBrainUnavailable(
            f"Knowledge Brain at {self.base_url} is unavailable ({type(last).__name__})."
        )

    def health(self) -> dict:
        return self._request("GET", "/health")

    def search(self, query: str, top_k: int = 4) -> dict:
        return self._request("POST", "/api/v1/search", json={"query": query, "top_k": top_k})

    def chat(self, question: str, conversation_id: Optional[str] = None) -> dict:
        return self._request("POST", "/api/v1/chat",
                             json={"question": question, "conversation_id": conversation_id})

    def create_task(self, question: str, context: str = "") -> dict:
        return self._request("POST", "/api/v1/tasks", json={"question": question, "context": context})
