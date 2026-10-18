"""Agent 4 - Proposal Agent, plus scope assembly and Agent 5 - Validation."""
from __future__ import annotations

import math
from typing import Optional

from .schemas import (AnalystOutput, Commercial, Estimate, Issue, KBFinding, Proposal, Requirement, Scope, ValidationReport)

GENERIC_ASSUMPTIONS = [
    "The client will give timely feedback (within 2 working days) and provide required content and access.",
    "Work is delivered in one iteration followed by one round of consolidated revisions.",
    "Third-party service fees (hosting, plugins, API usage) are paid by the client.",
]


def build_scope(a: AnalystOutput, reqs: list[Requirement], findings: list[KBFinding], estimate: Estimate) -> Scope:
    fmap = {f.requirement_id: f for f in findings}
    active = [r for r in reqs if r.status == "in_scope"]
    in_scope = []
    for r in active:
        f = fmap.get(r.id)
        tag = " [existing setting may suffice]" if f and f.existing_feature_candidate else ""
        in_scope.append(f"{r.id}: {r.text}{tag}")
    out_scope = [f"{r.id}: {r.text}" for r in reqs if r.status == "out_of_scope"]
    out_scope += ["Anything not listed under In scope, including hosting, ongoing maintenance and content writing unless stated.",
                  "Changes requested after sign-off (handled as a new estimate)."]
    criteria, open_q = [], list(a.open_questions)
    for r in active:
        stated = a.acceptance_criteria.get(r.id)
        if stated:
            criteria += [f"{r.id}: {c}" for c in stated]
        else:
            criteria.append(f"{r.id}: PROPOSED (not stated in the meeting) - '{r.text[:90]}' works as described and is accepted by the client in UAT.")
            open_q.append(f"{r.id}: What are the acceptance criteria for this requirement?")
    for r in active:
        if r.ambiguous:
            open_q.append(f"{r.id}: Clarify - {r.ambiguity_reason or 'requirement is vague'}.")
    for f in findings:
        open_q += [f"{f.requirement_id}: {q}" for q in f.unresolved_questions if f.evidence_status in ("unavailable", "insufficient")]
    open_q += [f"Conflict to resolve: {c}" for c in a.conflicts]
    assumptions = list(dict.fromkeys(GENERIC_ASSUMPTIONS + estimate.assumptions))
    objective = a.objective_hint or "Deliver the requirements discussed in the meeting."
    return Scope(objective=objective, requirements=reqs, in_scope=in_scope, out_of_scope=out_scope, assumptions=assumptions,
                 dependencies=list(dict.fromkeys(a.dependencies)) or ["No dependencies were mentioned; confirm client access and content."],
                 acceptance_criteria=criteria, open_questions=list(dict.fromkeys(open_q)))


class ProposalAgent:
    def __init__(self, hourly_rate: Optional[float], currency: str, hours_per_week: float):
        self.rate, self.currency, self.hpw = hourly_rate, currency, hours_per_week

    def run(self, client: str, scope: Scope, estimate: Estimate, findings: list[KBFinding], version: int) -> Proposal:
        total = estimate.total_hours
        weeks = max(1, math.ceil(total / self.hpw)) if total else 0
        if self.rate:
            comm = Commercial(status="illustrative", hourly_rate=self.rate, currency=self.currency, amount=round(total * self.rate, 2),
                              label=f"ILLUSTRATIVE ESTIMATE: {total:g} h x {self.rate:g} {self.currency}/h. Not an agreed price; subject to scoping and written approval.")
        else:
            comm = Commercial(status="not_configured", currency=self.currency,
                              label="Pricing not configured: no hourly rate was supplied. Set HOURLY_RATE to produce an illustrative figure.")
        existing = [f for f in findings if f.existing_feature_candidate]
        custom = [f for f in findings if f.custom_development_likely]
        solution = (f"We propose to deliver {len(scope.in_scope)} in-scope item(s). "
                    f"{len(existing)} may be achievable by configuring existing platform settings (pending confirmation), "
                    f"and {len(custom)} are expected to need custom development. Hour figures: {total:g} h total ({estimate.basis}).")
        return Proposal(
            executive_summary=f"{client}: {scope.objective} This proposal (version {version}) covers {len(scope.in_scope)} requirement(s), "
                              f"an estimated {total:g} developer hours over about {weeks} week(s), with {len(scope.open_questions)} open question(s) to resolve.",
            client_requirements=scope.in_scope, proposed_solution=solution,
            deliverables=[t.name for t in estimate.tasks if not t.id.startswith(("PM", "DEPLOY"))] + ["Deployment & handover notes"],
            timeline={"estimated_weeks": weeks, "assumption": f"{self.hpw:g} productive team hours per week; excludes client review time."},
            commercial=comm, exclusions=scope.out_of_scope,
            risks_and_assumptions=scope.assumptions + [f"Risk: {q}" for q in scope.open_questions[:5]],
            approval={"status": "DRAFT - NOT APPROVED", "text": "This document must be reviewed and approved by a human before it is sent to the client.",
                      "client_signature": "", "date": ""})


class Validator:
    REQUIRED_PROPOSAL = ["executive_summary", "client_requirements", "proposed_solution", "deliverables", "timeline",
                         "commercial", "exclusions", "risks_and_assumptions", "approval"]

    def run(self, a: AnalystOutput, scope: Scope, estimate: Estimate, findings: list[KBFinding], proposal: Proposal,
            rate_configured: bool) -> ValidationReport:
        issues: list[Issue] = []
        E, W = "error", "warning"
        if a.input_status == "insufficient":
            issues.append(Issue(severity=E, message="Transcript was empty/too short or contained no recognisable requirements."))
        if a.input_status == "possibly_truncated":
            issues.append(Issue(severity=W, message="Transcript may be truncated; some requirements could be missing."))
        in_ids = {r.id for r in scope.requirements if r.status == "in_scope"}
        out_ids = {r.id for r in scope.requirements if r.status == "out_of_scope"}
        if in_ids & out_ids:
            issues.append(Issue(severity=E, message="A requirement is both in scope and out of scope."))
        covered = {rid for t in estimate.tasks for rid in t.requirement_ids}
        for rid in sorted(in_ids - covered):
            issues.append(Issue(severity=E, message=f"In-scope requirement {rid} has no estimated task."))
        if abs(sum(t.hours for t in estimate.tasks) - estimate.total_hours) > 0.01:
            issues.append(Issue(severity=E, message="Total hours do not equal the sum of task hours."))
        for t in estimate.tasks:
            if not t.reasoning.strip():
                issues.append(Issue(severity=W, message=f"Task {t.id} has no reasoning."))
        for f in findings:
            if f.existing_feature_candidate and not f.evidence:
                issues.append(Issue(severity=E, message=f"{f.requirement_id}: claims an existing feature without evidence."))
        for r in scope.requirements:
            if r.ambiguous and r.status == "in_scope" and not any(r.id in q for q in scope.open_questions):
                issues.append(Issue(severity=W, message=f"Ambiguous requirement {r.id} has no open question."))
        if a.conflicts:
            issues.append(Issue(severity=W, message=f"{len(a.conflicts)} conflicting requirement(s) need client clarification."))
        for k in self.REQUIRED_PROPOSAL:
            v = getattr(proposal, k, None)
            if v in (None, "", [], {}):
                issues.append(Issue(severity=E, message=f"Proposal section '{k}' is empty."))
        if not rate_configured and proposal.commercial.amount is not None:
            issues.append(Issue(severity=E, message="A price was produced although no hourly rate is configured."))
        if any(f.evidence_status == "unavailable" for f in findings):
            issues.append(Issue(severity=W, message="Knowledge Brain was unavailable for some requirements; existing features were not checked."))
        return ValidationReport(passed=not any(i.severity == "error" for i in issues), issues=issues)
