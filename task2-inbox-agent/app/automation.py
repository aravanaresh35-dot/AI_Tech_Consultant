"""Conservative auto-send eligibility.

DEFINITIONS (also in DESIGN.md):
* Category      = the email's final category (the AI category, or the one a human corrected).
* Eligible draft= category not in NEVER_AUTO, evidence status 'supported' (or not needed), no sensitive keywords,
                  no prompt-injection signal, not ambiguous, Knowledge Brain was reachable.
* Unchanged     = a human APPROVED the draft and its text equals the original after whitespace normalisation.
* Streak        = consecutive ELIGIBLE drafts of that category that were approved unchanged. Any eligible draft that is
                  edited, replaced or rejected resets the streak to 0. Non-eligible drafts are ignored (neither count nor reset).
* Eligible category = streak >= AUTO_SEND_THRESHOLD (default 20) and not revoked and not in NEVER_AUTO.
* Revocation    = (a) any later eligible draft that is edited/replaced/rejected, (b) a feedback outcome of 'bad',
                  (c) a failed evaluation recorded for the category. Revoked categories restart from streak 0.
"""
from __future__ import annotations

import re

from .db import Database
from .safety import NEVER_AUTO


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


class AutomationTracker:
    def __init__(self, db: Database, threshold: int):
        self.db, self.threshold = db, threshold

    def _row(self, category: str) -> dict:
        row = self.db.one("SELECT * FROM category_stats WHERE category=?", (category,))
        if not row:
            self.db.run("INSERT INTO category_stats(category) VALUES(?)", (category,))
            row = self.db.one("SELECT * FROM category_stats WHERE category=?", (category,))
        return row

    def record_review(self, category: str, action: str, eligible: bool) -> dict:
        row = self._row(category)
        streak, status, reason = row["streak"], row["status"], row["revoked_reason"]
        reviewed, unchanged = row["total_reviewed"] + 1, row["total_unchanged"] + (action == "approved_unchanged")
        if category in NEVER_AUTO:
            status, streak = "never_auto", 0
        elif eligible:
            if action == "approved_unchanged":
                streak += 1
                if streak >= self.threshold and status != "auto_eligible":
                    status, reason = "auto_eligible", None
            else:  # edited / replaced / rejected
                if status == "auto_eligible":
                    status, reason = "revoked", f"Human changed or rejected an eligible draft ({action})"
                streak = 0
        self._save(category, streak, status, reason, reviewed, unchanged)
        return self._row(category)

    def revoke(self, category: str, reason: str) -> dict:
        row = self._row(category)
        status = "never_auto" if category in NEVER_AUTO else ("revoked" if row["status"] == "auto_eligible" else row["status"])
        self._save(category, 0, status, reason if status == "revoked" else row["revoked_reason"],
                   row["total_reviewed"], row["total_unchanged"])
        return self._row(category)

    def _save(self, category, streak, status, reason, reviewed, unchanged):
        self.db.run("""UPDATE category_stats SET streak=?, status=?, revoked_reason=?, total_reviewed=?, total_unchanged=?,
                       updated_at=datetime('now') WHERE category=?""", (streak, status, reason, reviewed, unchanged, category))

    def is_auto_eligible(self, category: str) -> bool:
        return category not in NEVER_AUTO and self._row(category)["status"] == "auto_eligible"

    def status(self) -> list[dict]:
        from .safety import CATEGORIES
        out = []
        for cat in CATEGORIES:
            r = self._row(cat)
            recent = self.db.all("""SELECT action FROM feedback WHERE category=? AND eligible=1 ORDER BY id DESC LIMIT 20""", (cat,))
            edit_rate = (sum(1 for x in recent if x["action"] != "approved_unchanged") / len(recent)) if recent else None
            out.append({"category": cat, "status": r["status"], "streak": r["streak"], "threshold": self.threshold,
                        "remaining": max(0, self.threshold - r["streak"]) if cat not in NEVER_AUTO else None,
                        "recent_edit_rate": None if edit_rate is None else round(edit_rate, 3),
                        "total_reviewed": r["total_reviewed"], "total_unchanged": r["total_unchanged"],
                        "revoked_reason": r["revoked_reason"],
                        "note": "Human approval always required for this category." if cat in NEVER_AUTO else None})
        return out
