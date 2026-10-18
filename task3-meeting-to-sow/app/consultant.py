"""Agent 2 - Product Consultant. Asks the Knowledge Brain (HTTP) whether an existing feature may cover a requirement.

It never claims a feature exists unless the Knowledge Brain returned supporting evidence.
"""
from __future__ import annotations

from tech_common.kb_client import KnowledgeBrainClient, KnowledgeBrainUnavailable

from .schemas import EvidenceItem, KBFinding, Requirement


class ProductConsultant:
    def __init__(self, kb: KnowledgeBrainClient, top_k: int = 3):
        self.kb, self.top_k = kb, top_k

    def run(self, requirements: list[Requirement]) -> list[KBFinding]:
        return [self._one(r) for r in requirements if r.status == "in_scope"]

    def _one(self, r: Requirement) -> KBFinding:
        try:
            res = self.kb.search(r.text, self.top_k)
        except KnowledgeBrainUnavailable as exc:
            return KBFinding(requirement_id=r.id, query=r.text, evidence_status="unavailable", existing_feature_candidate=False,
                             custom_development_likely=None, confidence=0.0,
                             unresolved_questions=["Product knowledge was unavailable; existing features were not checked."],
                             statement=f"Not checked: {exc}")
        status = res["evidence_status"]
        ev = [EvidenceItem(title=p["title"], url=p["url"], snippet=p["snippet"][:240]) for p in res["passages"][:2]]
        conf = float(res.get("confidence", 0.0))
        if status == "supported" and ev and not r.ambiguous:
            return KBFinding(requirement_id=r.id, query=r.text, evidence_status=status, existing_feature_candidate=True,
                             custom_development_likely=False, confidence=conf, evidence=ev,
                             unresolved_questions=["Confirm with the client that the documented setting meets their need."],
                             statement=f"An existing setting may cover this (see '{ev[0].title}'). To be confirmed with the client.")
        if status in ("supported", "partial") and ev:
            return KBFinding(requirement_id=r.id, query=r.text, evidence_status="partial", existing_feature_candidate=False,
                             custom_development_likely=True, confidence=conf, evidence=ev,
                             unresolved_questions=["Documentation only partly matches (or the requirement is vague); verify whether a setting suffices."],
                             statement=f"Possibly related documentation exists ('{ev[0].title}') but it does not clearly cover the requirement; custom work is assumed.")
        return KBFinding(requirement_id=r.id, query=r.text, evidence_status="insufficient", existing_feature_candidate=False,
                         custom_development_likely=True, confidence=conf,
                         unresolved_questions=["No supporting documentation found. This is not proof the feature is missing; ask a product expert."],
                         statement="No documented existing feature found; custom development is assumed.")
