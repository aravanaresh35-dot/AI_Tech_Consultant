"""Task 1 settings, read from environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _b(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


@dataclass
class Settings:
    db_path: str = field(default_factory=lambda: os.environ.get("KB_DB_PATH", str(BASE_DIR / "data" / "kb.sqlite3")))
    sitemap_url: str = field(default_factory=lambda: os.environ.get(
        "SITEMAP_URL", "https://support.brilliantdirectories.com/support/sitemap.xml"))
    # "demo" = offline fixture site shipped in data/demo_site; "live" = real website
    crawl_source: str = field(default_factory=lambda: os.environ.get("CRAWL_SOURCE", "demo").lower())
    demo_site_dir: str = field(default_factory=lambda: os.environ.get(
        "DEMO_SITE_DIR", str(BASE_DIR / "data" / "demo_site")))
    batch_size: int = field(default_factory=lambda: int(os.environ.get("INGEST_BATCH_SIZE", "20")))
    max_pages: int = field(default_factory=lambda: int(os.environ.get("INGEST_MAX_PAGES", "200")))
    request_delay: float = field(default_factory=lambda: float(os.environ.get("REQUEST_DELAY_SECONDS", "1.0")))
    http_timeout: float = field(default_factory=lambda: float(os.environ.get("HTTP_TIMEOUT_SECONDS", "15")))
    http_retries: int = field(default_factory=lambda: int(os.environ.get("HTTP_RETRIES", "3")))
    user_agent: str = field(default_factory=lambda: os.environ.get(
        "CRAWLER_USER_AGENT", "AITechConsultantBot/1.0 (capstone project; polite crawler)"))
    analyze_images: bool = field(default_factory=lambda: _b("ANALYZE_IMAGES", "false"))
    max_image_bytes: int = field(default_factory=lambda: int(os.environ.get("MAX_IMAGE_BYTES", "3000000")))
    # retrieval
    top_k: int = field(default_factory=lambda: int(os.environ.get("RETRIEVAL_TOP_K", "4")))
    min_coverage_supported: float = field(default_factory=lambda: float(os.environ.get("MIN_COVERAGE_SUPPORTED", "0.6")))
    min_coverage_partial: float = field(default_factory=lambda: float(os.environ.get("MIN_COVERAGE_PARTIAL", "0.34")))
    # scheduler (daily sync). OFF unless explicitly enabled.
    sync_schedule_enabled: bool = field(default_factory=lambda: _b("SYNC_SCHEDULE_ENABLED", "false"))
    sync_hour_utc: int = field(default_factory=lambda: int(os.environ.get("SYNC_HOUR_UTC", "3")))
    max_question_chars: int = 2000
