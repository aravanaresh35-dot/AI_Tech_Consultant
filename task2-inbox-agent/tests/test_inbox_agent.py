"""Task 2 deterministic tests (no network, no paid APIs)."""
import json
import re
from pathlib import Path

import pytest
from conftest import drafted, new_email

from app.classifier import classify

DATA = json.loads((Path(__file__).resolve().parents[1] / "data" / "sample_emails.json").read_text())


def approve(c, eid, **body):
    return c.post(f"/api/v1/emails/{eid}/approve", json=body)


def status(c, cat):
    return next(x for x in c.get("/api/v1/automation-status").json()["categories"] if x["category"] == cat)


def run_unchanged(c, n, start=0, prefix="How do I enable feature"):
    for i in range(start, start + n):
        eid, d = drafted(c, subject=f"{prefix} {i}", body=f"{prefix} {i} {i*7919} in the settings? How do I turn it on?")
        assert d["eligible"] is True, d
        assert approve(c, eid).json()["action"] == "approved_unchanged"


# 1 dataset + classification accuracy
def test_dataset_has_50_plus_emails_across_all_categories():
    assert len(DATA) >= 50
    assert {r["expected_category"] for r in DATA} == {"product_how_to", "technical_issue", "refund_request", "complaint",
                                                      "new_project_inquiry", "quote_request", "follow_up", "other"}
    assert len({r["body"] for r in DATA}) == len(DATA)  # no duplicates


def test_classification_accuracy_on_dataset_is_reported_and_high():
    ok = sum(classify(r["subject"], r["body"], bool(r["previous_conversation"]))["category"] == r["expected_category"] for r in DATA)
    assert ok / len(DATA) >= 0.9, f"{ok}/{len(DATA)}"


@pytest.mark.parametrize("cat", ["refund_request", "complaint", "quote_request", "new_project_inquiry", "follow_up", "technical_issue", "product_how_to", "other"])
def test_each_category_classified_correctly_for_first_sample(cat):
    r = next(x for x in DATA if x["expected_category"] == cat)
    assert classify(r["subject"], r["body"], bool(r["previous_conversation"]))["category"] == cat


# 2 product question grounded
def test_product_question_is_grounded_with_evidence(client):
    _, d = drafted(client)
    assert d["category"] == "product_how_to" and d["evidence_status"] == "supported"
    assert d["evidence"][0]["url"].endswith("member-login.html") and "Enable Login Page" in d["draft_reply"]
    assert d["needs_human_review"] is False and d["mode"] == "demo" and "DEMO" in d["label"]


# 3 technical issue asks for details
def test_technical_issue_draft_asks_for_details(client):
    _, d = drafted(client, subject="Error saving", body="I get an error every time I save and the page is stuck.")
    assert d["category"] == "technical_issue" and "error message" in d["draft_reply"]


# 4 refund never invents policy, always human
def test_refund_requires_human_and_invents_no_terms(client):
    _, d = drafted(client, subject="Refund please", body="I was charged twice. Please refund the duplicate payment.")
    assert d["category"] == "refund_request" and d["needs_human_review"] and d["eligible"] is False
    low = d["draft_reply"].lower()
    assert not re.search(r"\$|\d+ ?days|guarantee|will be refunded|full refund", low)


# 5 complaint
def test_complaint_escalated(client):
    _, d = drafted(client, subject="Unacceptable", body="This is unacceptable, nobody replied for a week. Very unhappy.")
    assert d["category"] == "complaint" and d["needs_human_review"] and "escalated" in d["draft_reply"]


# 6 quote has no price / 7 new project
def test_quote_contains_no_price(client):
    _, d = drafted(client, subject="Quote", body="Please send a quote for a custom report with a budget of 3k.")
    assert d["category"] == "quote_request" and not re.search(r"[$€£]|\b\d{3,}\b", d["draft_reply"])


def test_new_project_inquiry(client):
    _, d = drafted(client, subject="New website project", body="We are launching a directory and are looking for a developer.")
    assert d["category"] == "new_project_inquiry" and "discovery call" in d["draft_reply"]


# 8 follow-up uses history
def test_follow_up_with_history(client):
    r = client.post("/api/v1/emails", json={"customer_name": "Oscar", "customer_email": "o@x.example", "subject": "Re: Map pins",
                                           "body": "Any update?", "previous_conversation": [{"from": "customer", "text": "pins wrong"}]})
    d = client.post(f"/api/v1/emails/{r.json()['id']}/draft").json()
    assert d["category"] == "follow_up"


# 9 ambiguous
def test_ambiguous_email_needs_review(client):
    _, d = drafted(client, subject="Hi", body="Hello")
    assert d["category"] == "other" and d["needs_human_review"] and any("ambiguous" in x.lower() for x in d["review_reasons"])


# 10 missing details / validation
def test_missing_name_and_invalid_input(client):
    _, d = drafted(client, name="", subject="Enable", body="How do I enable the member login page?")
    assert d["draft_reply"].startswith("Hello,")
    bad = client.post("/api/v1/emails", json={"customer_email": "not-an-email", "subject": "x", "body": "y"})
    assert bad.status_code == 422
    assert client.post("/api/v1/emails", json={"customer_email": "a@b.co", "subject": " ", "body": "y"}).status_code == 422


# 11 unsupported product claim
def test_no_product_facts_without_evidence(client, kb_state):
    kb_state.mode = "insufficient"
    _, d = drafted(client, subject="Biometric", body="How do I enable fingerprint login on the member page?")
    assert d["evidence_status"] == "insufficient" and d["needs_human_review"]
    assert "documentation" not in d["draft_reply"].lower() and "confirming" in d["draft_reply"]


# 12 malicious instructions
def test_prompt_injection_flagged_and_not_obeyed(client):
    inj = next(r for r in DATA if "IGNORE ALL PREVIOUS" in r["body"])
    _, d = drafted(client, subject=inj["subject"], body=inj["body"])
    assert d["injection_detected"] and d["needs_human_review"] and d["eligible"] is False
    low = d["draft_reply"].lower()
    assert "lifetime" not in low and "refund" not in low and "system prompt" not in low


# 13 KB unavailable
def test_knowledge_brain_unavailable_degrades_safely(client, kb_state):
    kb_state.mode = "down"
    _, d = drafted(client)
    assert d["evidence_status"] == "unavailable" and d["needs_human_review"] and d["eligible"] is False
    assert any("unavailable" in n for n in d["notes"])
    assert client.get("/health").json()["knowledge_brain"]["status"] == "unavailable"


# 14 draft quality basics
def test_draft_quality_basics(client):
    _, d = drafted(client)
    assert d["draft_reply"].rstrip().endswith("Support Team") and 40 < len(d["draft_reply"]) < 1500
    assert "[" not in d["draft_reply"] and d["summary"]


# 15 human editing stores diff
def test_human_edit_is_recorded_with_diff(client):
    eid, d = drafted(client)
    r = approve(client, eid, final_text=d["draft_reply"].replace("Thanks for your question.", "Thanks so much!"), reviewer="Kim").json()
    assert r["action"] == "approved_edited"
    fb = client.get(f"/api/v1/emails/{eid}/feedback").json()["items"][0]
    assert "Thanks so much!" in fb["diff"] and fb["original_draft"] == d["draft_reply"] and fb["prompt_version"] and fb["category"]


# 16 rejection
def test_rejection_queues_nothing(client):
    eid, _ = drafted(client)
    assert client.post(f"/api/v1/emails/{eid}/reject", json={"reason": "wrong tone"}).json()["queued"] is False
    assert client.get("/api/v1/outbound").json()["items"] == []
    assert client.get(f"/api/v1/emails/{eid}").json()["status"] == "rejected"
    assert approve(client, eid).status_code == 409


# 17 persistence
def test_feedback_and_streak_persist_across_restart(make_client, tmp_path):
    db = str(tmp_path / "inbox.sqlite3")
    c1 = make_client(db=db)
    run_unchanged(c1, 3)
    c2 = make_client(db=db)
    assert status(c2, "product_how_to")["streak"] == 3 and len(c2.get("/api/v1/feedback").json()["items"]) == 3


# 18 twenty-consecutive threshold
def test_threshold_requires_20_consecutive_unchanged(client):
    run_unchanged(client, 19)
    s = status(client, "product_how_to")
    assert s["streak"] == 19 and s["status"] == "manual_only" and s["remaining"] == 1
    run_unchanged(client, 1, start=19)
    assert status(client, "product_how_to")["status"] == "auto_eligible"


# 19 any change resets the streak
def test_edit_resets_streak_before_threshold(client):
    run_unchanged(client, 10)
    eid, d = drafted(client, subject="How do I enable feature x", body="How do I enable feature x in the settings? thanks")
    approve(client, eid, final_text=d["draft_reply"] + "\nPS: thanks!")
    assert status(client, "product_how_to")["streak"] == 0


# 20 revocation: edit after eligibility, failed evaluation, bad outcome
def test_revocation_paths(client):
    run_unchanged(client, 20)
    eid, d = drafted(client, subject="How do I enable feature y", body="How do I enable feature y in the settings? please")
    approve(client, eid, final_text="Totally different reply.")
    s = status(client, "product_how_to")
    assert s["status"] == "revoked" and s["streak"] == 0 and "changed" in s["revoked_reason"]
    run_unchanged(client, 20, start=100)
    assert status(client, "product_how_to")["status"] == "auto_eligible"
    client.post("/api/v1/automation/evaluations", json={"category": "product_how_to", "passed": False, "note": "hallucinated setting"})
    assert status(client, "product_how_to")["status"] == "revoked"
    run_unchanged(client, 20, start=200)
    eid, _ = drafted(client, subject="How do I enable feature z", body="How do I enable feature z in the settings? hello")
    approve(client, eid)
    client.post(f"/api/v1/emails/{eid}/feedback", json={"outcome": "bad", "note": "customer confused"})
    assert status(client, "product_how_to")["status"] == "revoked"


# 21 refunds/complaints can never become auto-eligible
def test_refund_never_auto_even_after_many_unchanged(client):
    for i in range(25):
        eid, d = drafted(client, subject=f"Refund please {i}", body=f"Please refund invoice number {i*31337}.")
        approve(client, eid)
    s = status(client, "refund_request")
    assert s["status"] == "never_auto" and s["streak"] == 0 and s["remaining"] is None


# 22 outbound queue is simulated; auto-queue off by default, on only when enabled and eligible
def test_outbound_queue_simulated_and_auto_requires_explicit_enable(make_client):
    c = make_client()
    eid, _ = drafted(c)
    approve(c, eid)
    ob = c.get("/api/v1/outbound").json()
    assert ob["mode"] == "SIMULATED_NOT_SENT" and ob["items"][0]["mode"] == "SIMULATED_NOT_SENT" and ob["items"][0]["sent_by"] == "human_approved"
    off = make_client()
    run_unchanged(off, 20)
    eid, d = drafted(off, subject="How do I enable feature q", body="How do I enable feature q in the settings? hi")
    assert d["auto_queued"] is False
    on = make_client(auto_send_enabled=True)
    run_unchanged(on, 20)
    eid, d = drafted(on, subject="How do I enable feature q", body="How do I enable feature q in the settings? hi")
    assert d["auto_queued"] is True
    assert on.get("/api/v1/outbound").json()["items"][0]["sent_by"] == "auto"


# 23 non-eligible drafts neither count nor reset
def test_ineligible_drafts_do_not_affect_streak(client, kb_state):
    run_unchanged(client, 5)
    kb_state.mode = "insufficient"
    eid, d = drafted(client, subject="How do I enable fingerprint", body="How do I enable fingerprint login in settings?")
    assert d["eligible"] is False
    approve(client, eid, final_text="Custom reply by a human.")
    assert status(client, "product_how_to")["streak"] == 5


# 24 learning: approved human reply is reused for near-duplicate emails
def test_approved_reply_memory_reuses_human_text(client):
    eid, _ = drafted(client, subject="Domain help", body="Where can I connect our own domain name to the site?")
    client.post(f"/api/v1/emails/{eid}/replace", json={"final_text": "Hi! Use Settings > Domain and add the CNAME shown.", "reviewer": "Sam"})
    _, d2 = drafted(client, subject="Domain help", body="Where can I connect our own domain name to the site?", addr="b@x.example")
    assert d2["source"] == "approved_reply_memory" and d2["draft_reply"].startswith("Hi! Use Settings") and "memory" in d2["prompt_version"]


# 25 metrics / edit rate
def test_metrics_report_edit_rate_by_prompt_version(client):
    run_unchanged(client, 2)
    eid, d = drafted(client, subject="How do I enable feature m", body="How do I enable feature m in the settings? hello")
    approve(client, eid, final_text="changed")
    m = client.get("/api/v1/automation-status").json()["metrics"]["by_category_and_prompt_version"]
    assert sum(r["n"] for r in m) == 3 and sum(r["unchanged"] for r in m) == 2
    by = {r["prompt_version"]: r for r in m}  # near-duplicate email reused approved reply -> own prompt_version bucket
    assert by["draft-v1-template"]["edit_rate"] == 0.0 and by["draft-v1+memory"]["edit_rate"] == 0.5


# 26 workflow errors
def test_workflow_errors(client):
    assert client.get("/api/v1/emails/999").status_code == 404
    eid = new_email(client)
    assert approve(client, eid).status_code == 409  # no draft yet
    assert client.post("/api/v1/emails/999/draft").status_code == 404
    assert client.post(f"/api/v1/emails/{eid}/replace", json={"final_text": " "}).status_code == 422


# 27 live model path (TEST DOUBLE): model output used, outage falls back to template
class FakeAI:
    is_live, mode, model = True, "live", "test-double"

    def __init__(self, fail=False):
        self.fail = fail

    def generate_json(self, system, user, schema, version, max_tokens=0):
        from tech_common.ai import AIUnavailable
        if self.fail:
            raise AIUnavailable("down")
        if schema.__name__ == "LiveClass":
            return schema(category="product_how_to"), None
        assert "UNTRUSTED" in system and "<customer_email>" in user and "EVIDENCE" in user
        return schema(summary="Customer asks about login page.", draft_body="Hi Ana, model-written reply.\n\nSupport Team"), None


def test_live_path_uses_model_and_falls_back(make_client):
    _, d = drafted(make_client(ai=FakeAI()))
    assert d["source"] == "model" and d["mode"] == "live" and d["draft_reply"].startswith("Hi Ana, model-written")
    _, d2 = drafted(make_client(ai=FakeAI(fail=True)))
    assert d2["source"] == "template" and d2["mode"] == "demo" and d2["notes"]
