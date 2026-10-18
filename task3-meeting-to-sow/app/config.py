from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _opt_float(name: str):
    v = os.environ.get(name, "").strip()
    try:
        return float(v) if v else None
    except ValueError:
        return None


@dataclass
class Settings:
    db_path: str = field(default_factory=lambda: os.environ.get("SOW_DB_PATH", str(BASE_DIR / "data" / "sow.sqlite3")))
    max_transcript_chars: int = field(default_factory=lambda: int(os.environ.get("MAX_TRANSCRIPT_CHARS", "300000")))
    min_transcript_chars: int = 60
    # Pricing is OPTIONAL. If unset the proposal says so and shows no money amount.
    hourly_rate: float | None = field(default_factory=lambda: _opt_float("HOURLY_RATE"))
    currency: str = field(default_factory=lambda: os.environ.get("CURRENCY", "USD"))
    team_hours_per_week: float = field(default_factory=lambda: float(os.environ.get("TEAM_HOURS_PER_WEEK", "30")))
    kb_top_k: int = 3
