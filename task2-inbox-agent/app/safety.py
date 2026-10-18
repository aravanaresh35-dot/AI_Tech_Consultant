"""Deterministic safety checks that ALWAYS run, even when a live model is used."""
from __future__ import annotations

import re

CATEGORIES = ["product_how_to", "technical_issue", "refund_request", "complaint",
              "new_project_inquiry", "quote_request", "follow_up", "other"]
# These categories can never be sent automatically, no matter how many drafts were approved.
NEVER_AUTO = {"refund_request", "complaint"}

SENSITIVE = re.compile(
    r"\b(lawyer|attorney|lawsuit|sue\b|legal action|legal team|court|gdpr|data breach|hacked|"
    r"chargeback|dispute the charge|harass|discriminat|threat|police|regulator|fraud|"
    r"medical|self-harm|suicide)\b", re.I)
INJECTION = re.compile(
    r"(ignore (all |any |the )?(previous|prior|above) (instructions|rules)|disregard (the )?(system|previous)|"
    r"system prompt|you are now|act as (an? )?(admin|developer)|reveal (your|the) (prompt|instructions)|"
    r"forward (this|all|the) .{0,40}(to|@)|send .{0,40}(password|api key|credentials)|"
    r"approve (the )?refund automatically|bypass)", re.I)


def sensitive_flags(text: str) -> list[str]:
    return sorted({m.group(0).lower() for m in SENSITIVE.finditer(text)})


def injection_detected(text: str) -> bool:
    return bool(INJECTION.search(text))
