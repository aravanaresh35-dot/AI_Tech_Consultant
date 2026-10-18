"""Rule-based classifier (deterministic, used in demo mode and as the safety baseline).

In live mode the model may propose a category, but safety flags always come from rules.
"""
from __future__ import annotations

import re

RULES: list[tuple[str, list[str]]] = [  # order = tie-break priority
    ("refund_request", ["refund", "money back", "reimburse", "charged twice", "double charged", "cancel my subscription and"]),
    ("complaint", ["unacceptable", "terrible", "furious", "disappointed", "worst", "complaint", "fed up", "ridiculous",
                   "awful", "very unhappy", "angry", "no one has replied", "nobody replied"]),
    ("technical_issue", ["error", "not working", "doesn't work", "does not work", "broken", "bug", "crash", "can't log",
                         "cannot log", "failed", "fails", "won't load", "not loading", "blank page", "stuck", "500"]),
    ("quote_request", ["quote", "estimate", "how much would", "how much does it cost to", "price for", "pricing for",
                       "cost to build", "budget of"]),
    ("new_project_inquiry", ["new project", "build us", "redesign", "we are launching", "we're launching", "looking to hire",
                             "looking for a developer", "proposal", "start a project", "new website", "migrate our"]),
    ("follow_up", ["following up", "follow up", "follow-up", "any update", "checking in", "circling back",
                   "still waiting", "haven't heard", "just checking"]),
    ("product_how_to", ["how do i", "how can i", "how to", "where can i", "where do i", "is it possible", "can i ",
                        "set up", "configure", "enable", "turn on", "change the", "add a", "import", "export"]),
]


def classify(subject: str, body: str, has_history: bool = False) -> dict:
    text = f"{subject}\n{body}".lower()
    scores: dict[str, int] = {}
    for cat, kws in RULES:
        n = sum(1 for k in kws if k in text)
        if n:
            scores[cat] = n
    if has_history and re.match(r"\s*(re|fwd?):", subject, re.I):
        scores["follow_up"] = scores.get("follow_up", 0) + 1
    if not scores:
        return {"category": "other", "ambiguous": len(body.split()) < 8, "scores": {}}
    order = [c for c, _ in RULES]
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], order.index(kv[0])))
    top = ranked[0]
    ambiguous = len(ranked) > 1 and ranked[1][1] == top[1] and top[0] not in ("refund_request", "complaint")
    return {"category": top[0], "ambiguous": ambiguous, "scores": scores}


def summarize(subject: str, body: str, limit: int = 160) -> str:
    first = re.split(r"(?<=[.!?])\s+", body.strip())[0] if body.strip() else subject
    return (first if len(first) <= limit else first[: limit - 1] + "…")
