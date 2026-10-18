from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    db_path: str = field(default_factory=lambda: os.environ.get("INBOX_DB_PATH", str(BASE_DIR / "data" / "inbox.sqlite3")))
    auto_send_threshold: int = field(default_factory=lambda: int(os.environ.get("AUTO_SEND_THRESHOLD", "20")))
    # Even when a category is eligible, nothing is auto-queued unless this is explicitly true.
    auto_send_enabled: bool = field(default_factory=lambda: os.environ.get("AUTO_SEND_ENABLED", "false").lower() == "true")
    memory_similarity: float = field(default_factory=lambda: float(os.environ.get("MEMORY_SIMILARITY", "0.7")))
    max_body_chars: int = 8000
    base_prompt_version: str = "draft-v1"
