#!/usr/bin/env python3
"""End-to-end smoke test against RUNNING services (./run.sh). Exits non-zero on failure."""
import sys
from pathlib import Path

import httpx

KB, INBOX, SOW = "http://localhost:8001", "http://localhost:8002", "http://localhost:8003"
ROOT = Path(__file__).resolve().parent.parent
fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {detail}"))
    if not cond:
        fails.append(name)


with httpx.Client(timeout=30) as c:
    for n, u in (("knowledge-brain", KB), ("inbox-agent", INBOX), ("meeting-to-sow", SOW)):
        check(f"{n} health", c.get(f"{u}/health").json().get("status") == "ok")
    r = c.post(f"{KB}/api/v1/chat", json={"question": "How do I enable the member login page?"}).json()
    check("KB chat answers with a source", bool(r.get("sources")) and not r.get("needs_human_review"), r)
    r = c.post(f"{KB}/api/v1/chat", json={"question": "What is the warranty on your hardware drones?"}).json()
    check("KB escalates unknown question", r.get("needs_human_review") is True and r.get("task_id"), r)
    e = c.post(f"{INBOX}/api/v1/emails", json={"customer_name": "Ana", "customer_email": "ana@example.com",
                                               "subject": "Login page", "body": "How do I enable the member login page?"}).json()
    d = c.post(f"{INBOX}/api/v1/emails/{e['id']}/draft").json()
    check("Inbox drafts via Knowledge Brain HTTP", bool(d), d)
    ob = c.get(f"{INBOX}/api/v1/outbound").json()
    check("Inbox outbound is simulated", ob["mode"] == "SIMULATED_NOT_SENT")
    t1 = (ROOT / "task3-meeting-to-sow/sample_transcripts/01_website_improvement.txt").read_text()
    t3 = (ROOT / "task3-meeting-to-sow/sample_transcripts/03_follow_up_changes.txt").read_text()
    m = c.post(f"{SOW}/api/v1/meetings", json={"title": "Smoke", "client_name": "Smoke Co", "transcript": t1}).json()["id"]
    a = c.post(f"{SOW}/api/v1/meetings/{m}/analyze").json()
    check("SOW analyze v1", a.get("version") == 1 and a.get("total_hours", 0) > 0, a)
    f = c.get(f"{SOW}/api/v1/meetings/{m}/scope").json()["product_findings"]
    check("SOW queried Knowledge Brain", any(x["evidence_status"] != "unavailable" for x in f), f[:1])
    c.post(f"{SOW}/api/v1/meetings/{m}/follow-up", json={"transcript": t3})
    cmp_ = c.get(f"{SOW}/api/v1/meetings/{m}/comparison").json()["comparison"]
    check("SOW follow-up comparison", bool(cmp_["added"] or cmp_["removed"] or cmp_["modified"]))
    ap = c.post(f"{SOW}/api/v1/meetings/{m}/approve", json={"approver": "smoke"}).json()
    check("SOW approval is internal only", ap["dispatched_to_client"] is False)
sys.exit(1 if fails else 0)
