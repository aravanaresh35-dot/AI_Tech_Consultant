from __future__ import annotations

import difflib
import json
import logging
from typing import Optional

from tech_common.logging_setup import log

from .automation import AutomationTracker, normalize
from .config import Settings
from .db import Database
from .drafting import DraftingService
from .safety import CATEGORIES

logger = logging.getLogger("inbox")


class InboxService:
    def __init__(self, db: Database, drafting: DraftingService, tracker: AutomationTracker, settings: Settings):
        self.db, self.drafting, self.tracker, self.s = db, drafting, tracker, settings

    # ---- emails ---------------------------------------------------------------------------------
    def create_email(self, name, address, subject, body, history) -> dict:
        eid = self.db.run("INSERT INTO emails(customer_name,customer_email,subject,body,previous_conversation) VALUES(?,?,?,?,?)",
                          (name, address, subject, body, json.dumps(history or [])))
        return self.get_email(eid)

    def get_email(self, eid: int) -> Optional[dict]:
        e = self.db.one("SELECT * FROM emails WHERE id=?", (eid,))
        if not e:
            return None
        e["previous_conversation"] = json.loads(e["previous_conversation"])
        d = self.db.one("SELECT * FROM drafts WHERE email_id=? ORDER BY id DESC LIMIT 1", (eid,))
        e["latest_draft"] = ({**json.loads(d["payload"]), "draft_id": d["id"]}) if d else None
        e["feedback"] = self.db.all("SELECT * FROM feedback WHERE email_id=? ORDER BY id", (eid,))
        return e

    def list_emails(self, status: Optional[str] = None) -> list[dict]:
        q = "SELECT id,customer_name,customer_email,subject,category,status,created_at FROM emails"
        return self.db.all(q + (" WHERE status=?" if status else "") + " ORDER BY id DESC", (status,) if status else ())

    # ---- drafting -------------------------------------------------------------------------------
    def draft(self, eid: int) -> dict:
        e = self.get_email(eid)
        if not e:
            raise KeyError(eid)
        if e["status"] in ("approved", "rejected"):
            raise ValueError(f"Email already {e['status']}")
        d = self.drafting.generate(e)
        did = self.db.run("""INSERT INTO drafts(email_id,payload,body,category,mode,model,prompt_version,eligible)
                             VALUES(?,?,?,?,?,?,?,?)""", (eid, json.dumps(d), d["draft_reply"], d["category"], d["mode"],
                                                          d["model"], d["prompt_version"], int(d["eligible"])))
        self.db.run("UPDATE emails SET category=?, status='drafted' WHERE id=?", (d["category"], eid))
        # Optional auto-queue: only if explicitly enabled AND the category earned eligibility AND this draft is eligible.
        d["auto_queued"] = False
        if self.s.auto_send_enabled and d["eligible"] and not d["needs_human_review"] and self.tracker.is_auto_eligible(d["category"]):
            self._queue(e, d["draft_reply"], "auto")
            self.db.run("UPDATE emails SET status='approved' WHERE id=?", (eid,))
            self._feedback(e, did, d["category"], "auto_sent", d["draft_reply"], d["draft_reply"], d, "system", None)
            d["auto_queued"] = True
        log(logger, "draft_created", email_id=eid, category=d["category"], mode=d["mode"], eligible=d["eligible"])
        return {**d, "draft_id": did}

    # ---- human review -----------------------------------------------------------------------------
    def _latest(self, eid: int):
        e = self.get_email(eid)
        if not e:
            raise KeyError(eid)
        if not e["latest_draft"]:
            raise ValueError("Generate a draft first")
        if e["status"] in ("approved", "rejected"):
            raise ValueError(f"Email already {e['status']}")
        return e, e["latest_draft"]

    def _queue(self, e: dict, body: str, by: str):
        # SIMULATED ONLY: nothing is ever sent to a real mail server.
        self.db.run("INSERT INTO outbound(email_id,to_address,subject,body,sent_by) VALUES(?,?,?,?,?)",
                    (e["id"], e["customer_email"], "Re: " + e["subject"], body, by))

    def _feedback(self, e, did, category, action, original, final, d, reviewer, reason):
        diff = "\n".join(difflib.unified_diff((original or "").splitlines(), (final or "").splitlines(),
                                              "ai_draft", "final", lineterm="", n=1)) if final != original else ""
        original_email = json.dumps({"subject": e["subject"], "body": e["body"], "customer_email": e["customer_email"]})
        self.db.run("""INSERT INTO feedback(email_id,draft_id,category,action,original_email,original_draft,final_text,diff,
                       eligible,model,prompt_version,mode,reviewer,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (e["id"], did, category, action, original_email, original, final, diff, int(d["eligible"]),
                     d.get("model"), d["prompt_version"], d["mode"], reviewer, reason))

    def review(self, eid: int, action: str, final_text: Optional[str], reviewer: str, category: Optional[str], reason: Optional[str]) -> dict:
        e, d = self._latest(eid)
        cat = category if category in CATEGORIES else d["category"]
        original = d["draft_reply"]
        if action == "approve":
            same = final_text is None or normalize(final_text) == normalize(original)
            act, final = ("approved_unchanged", original) if same else ("approved_edited", final_text)
            if cat != d["category"] and same:
                act = "approved_edited"  # category corrected by human = a change
        elif action == "replace":
            act, final = "replaced", final_text
        else:
            act, final = "rejected", None
        self._feedback(e, d["draft_id"], cat, act, original, final, d, reviewer, reason)
        stats = self.tracker.record_review(cat, act, bool(d["eligible"]) and cat == d["category"])
        if act != "rejected":
            self._queue(e, final, "human_approved")
        self.db.run("UPDATE emails SET status=?, category=? WHERE id=?",
                    ("rejected" if act == "rejected" else "approved", cat, eid))
        log(logger, "review", email_id=eid, action=act, category=cat, streak=stats["streak"], status=stats["status"])
        return {"email_id": eid, "action": act, "category": cat, "automation": stats,
                "queued": act != "rejected", "queue_mode": "SIMULATED_NOT_SENT"}

    def record_outcome(self, eid: int, outcome: str, note: Optional[str]) -> dict:
        e = self.get_email(eid)
        if not e:
            raise KeyError(eid)
        last = self.db.one("SELECT id, category FROM feedback WHERE email_id=? ORDER BY id DESC LIMIT 1", (eid,))
        if not last:
            raise ValueError("No reviewed draft for this email")
        self.db.run("UPDATE feedback SET evaluation_outcome=?, reason=COALESCE(?,reason) WHERE id=?", (outcome, note, last["id"]))
        stats = None
        if outcome == "bad":
            stats = self.tracker.revoke(last["category"], f"Post-send quality outcome 'bad' on email {eid}")
        return {"email_id": eid, "outcome": outcome, "automation": stats}

    def record_evaluation(self, category: str, passed: bool, note: str = "") -> dict:
        if category not in CATEGORIES:
            raise ValueError("Unknown category")
        if not passed:
            return self.tracker.revoke(category, f"Failed evaluation: {note or 'no detail'}")
        return self.tracker._row(category)

    def history(self, limit: int = 100) -> list[dict]:
        return self.db.all("""SELECT id,email_id,category,action,model,prompt_version,mode,reviewer,reason,evaluation_outcome,
                              diff,created_at FROM feedback ORDER BY id DESC LIMIT ?""", (limit,))

    def outbound(self) -> list[dict]:
        return self.db.all("SELECT * FROM outbound ORDER BY id DESC")

    def metrics(self) -> dict:
        rows = self.db.all("""SELECT category, prompt_version, COUNT(*) n,
                              SUM(action='approved_unchanged') unchanged FROM feedback
                              WHERE action!='auto_sent' GROUP BY category, prompt_version""")
        for r in rows:
            r["edit_rate"] = round(1 - (r["unchanged"] or 0) / r["n"], 3)
        return {"by_category_and_prompt_version": rows}
