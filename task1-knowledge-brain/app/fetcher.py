"""Fetchers. `HttpFetcher` is the polite live crawler; `LocalFetcher` serves the offline demo site."""
from __future__ import annotations

import logging
import time
import urllib.robotparser
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("fetcher")


class FetchError(RuntimeError):
    pass


class Fetcher(Protocol):
    def get_text(self, url: str) -> str: ...
    def get_bytes(self, url: str, max_bytes: int) -> tuple[bytes, str]: ...


class HttpFetcher:
    """Sequential (no concurrency), delayed, retrying, robots.txt-aware."""

    def __init__(self, user_agent: str, timeout: float = 15, retries: int = 3, delay: float = 1.0,
                 transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        self.ua, self.retries, self.delay, self._sleep = user_agent, retries, delay, sleep
        self.client = httpx.Client(timeout=timeout, headers={"User-Agent": user_agent},
                                   follow_redirects=True, transport=transport)
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._last = 0.0

    def _allowed(self, url: str) -> bool:
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.client.get(f"{origin}/robots.txt")
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
                self._robots[origin] = rp
            except httpx.HTTPError:
                self._robots[origin] = None  # robots unreachable -> proceed politely
        rp = self._robots[origin]
        return True if rp is None else rp.can_fetch(self.ua, url)

    def _get(self, url: str) -> httpx.Response:
        if not self._allowed(url):
            raise FetchError(f"Blocked by robots.txt: {url}")
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                self._sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.client.get(url)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError("transient", request=r.request, response=r)
                if r.status_code >= 400:
                    raise FetchError(f"HTTP {r.status_code} for {url}")
                return r
            except FetchError:
                raise
            except httpx.HTTPError as exc:
                last = exc
                if attempt < self.retries:
                    self._sleep(min(2 ** attempt, 20))  # exponential backoff
        raise FetchError(f"Giving up on {url}: {type(last).__name__}")

    def get_text(self, url: str) -> str:
        return self._get(url).text

    def get_bytes(self, url: str, max_bytes: int) -> tuple[bytes, str]:
        r = self._get(url)
        if len(r.content) > max_bytes:
            raise FetchError("Image too large")
        return r.content, r.headers.get("content-type", "application/octet-stream")


class LocalFetcher:
    """Maps https://demo.example/... URLs onto files in the demo_site directory (no network)."""

    HOST = "https://demo.example"

    def __init__(self, root: str):
        self.root = Path(root)

    def _path(self, url: str) -> Path:
        if not url.startswith(self.HOST):
            raise FetchError(f"Not a demo URL: {url}")
        rel = url[len(self.HOST):].lstrip("/") or "index.html"
        p = (self.root / rel).resolve()
        if self.root.resolve() not in p.parents and p != self.root.resolve():
            raise FetchError("Path escapes demo root")
        if not p.is_file():
            raise FetchError(f"HTTP 404 for {url}")
        return p

    def get_text(self, url: str) -> str:
        return self._path(url).read_text(encoding="utf-8")

    def get_bytes(self, url: str, max_bytes: int) -> tuple[bytes, str]:
        p = self._path(url)
        data = p.read_bytes()
        if len(data) > max_bytes:
            raise FetchError("Image too large")
        return data, "image/png" if p.suffix == ".png" else "application/octet-stream"
