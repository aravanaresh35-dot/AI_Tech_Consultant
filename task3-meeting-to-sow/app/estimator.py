"""Agent 3 - Estimation Agent. Demo mode uses a transparent keyword-based heuristic; hours are NOT expert estimates."""
from __future__ import annotations

import math
import re

from tech_common.ai import AIClient, AIUnavailable

from .schemas import PROMPT_VERSION, Estimate, EstimateTask, KBFinding, Requirement

# (regex, base hours for a custom build, label)
SIZE_RULES = [
    (r"booking|appointment|schedul|reservation", 48, "booking/scheduling workflow"),
    (r"payment|checkout|invoice|subscription|billing", 32, "payment flow"),
    (r"integrat|api|crm|zapier|webhook|sync", 32, "third-party integration"),
    (r"migrat|import", 32, "data migration"),
    (r"report|dashboard|analytics", 24, "reporting/dashboard"),
    (r"notification|email|sms|reminder", 16, "notification feature"),
    (r"login|auth|account|permission|role", 20, "authentication/permissions"),
    (r"search|filter", 20, "search/filter"),
    (r"design|redesign|layout|theme|branding", 40, "design work"),
    (r"form|field", 10, "form/field change"),
]
DEFAULT_HOURS = 16


def _round(h: float) -> float:
    return round(h * 2) / 2


class EstimationAgent:
    def __init__(self, ai: AIClient):
        self.ai = ai

    def run(self, requirements: list[Requirement], findings: list[KBFinding]) -> Estimate:
        if self.ai.is_live:
            try:
                return self._live(requirements, findings)
            except AIUnavailable:
                pass
        return self._demo(requirements, findings)

    def _demo(self, requirements: list[Requirement], findings: list[KBFinding]) -> Estimate:
        fmap = {f.requirement_id: f for f in findings}
        tasks: list[EstimateTask] = []
        for r in requirements:
            if r.status != "in_scope":
                continue
            f = fmap.get(r.id)
            risk = "high" if (r.ambiguous and (not f or f.custom_development_likely is not False)) else ("medium" if r.ambiguous or (f and f.custom_development_likely is None) else "low")
            if f and f.existing_feature_candidate:
                tasks.append(EstimateTask(id=f"{r.id}-cfg", name=f"Configure existing feature ({r.id})",
                                          description=f"Configure the documented setting that may satisfy: {r.text}", hours=3,
                                          reasoning="Existing setting found in documentation; hours cover configuration, testing and a client walkthrough.",
                                          dependencies=[], risk=risk if risk != "high" else "medium", requirement_ids=[r.id]))
                continue
            base, label = DEFAULT_HOURS, "unclassified feature (default)"
            for pat, hrs, lab in SIZE_RULES:
                if re.search(pat, r.text, re.I):
                    base, label = hrs, lab
                    break
            if r.ambiguous:
                base *= 1.25  # uncertainty buffer
            parts = [("design", "Technical design", 0.15), ("build", "Implementation", 0.65), ("qa", "Testing & client UAT", 0.20)]
            prev = None
            for key, nm, share in parts:
                tid = f"{r.id}-{key}"
                tasks.append(EstimateTask(
                    id=tid, name=f"{nm} ({r.id})", description=f"{nm} for: {r.text}", hours=_round(base * share),
                    reasoning=f"Heuristic: {label} baseline {base:g}h x {int(share*100)}%." + (" +25% buffer for vague wording." if r.ambiguous else ""),
                    dependencies=[prev] if prev else [], risk=risk, requirement_ids=[r.id]))
                prev = tid
        build_hours = sum(t.hours for t in tasks)
        if tasks:
            pm = _round(max(2, build_hours * 0.10))
            tasks.append(EstimateTask(id="PM", name="Project management & communication", description="Planning, status updates, client calls.",
                                      hours=pm, reasoning="Heuristic: 10% of delivery hours (minimum 2h).", dependencies=[], risk="low", requirement_ids=[]))
            tasks.append(EstimateTask(id="DEPLOY", name="Deployment & handover", description="Release, smoke test, handover notes.",
                                      hours=4, reasoning="Fixed allowance.", dependencies=[t.id for t in tasks if t.id.endswith("-qa") or t.id.endswith("-cfg")][:10],
                                      risk="low", requirement_ids=[]))
        total = _round(sum(t.hours for t in tasks))
        return Estimate(tasks=tasks, total_hours=total, basis="heuristic_demo", assumptions=[
            "DEMO heuristic estimate from keyword rules, not an expert estimate; replace with developer review before quoting.",
            "Each hour figure assumes one developer and a prompt client response (feedback within 2 working days).",
            "Existing-feature items assume the documented setting behaves as described.",
            "Requirements marked ambiguous include a 25% uncertainty buffer."])

    def _live(self, requirements: list[Requirement], findings: list[KBFinding]) -> Estimate:
        reqs = "\n".join(f"{r.id}: {r.text} (ambiguous={r.ambiguous})" for r in requirements if r.status == "in_scope")
        fx = "\n".join(f"{f.requirement_id}: existing_feature_candidate={f.existing_feature_candidate}; {f.statement}" for f in findings)
        system = ("You are a senior estimator for a web/SaaS agency. Break each in-scope requirement into tasks with hour estimates, "
                  "reasoning, dependencies, risk (low|medium|high) and requirement_ids. Requirements marked as existing-feature candidates "
                  "should be small configuration tasks. State assumptions. Do not invent requirements. Return JSON: "
                  "{tasks:[{id,name,description,hours,reasoning,dependencies,risk,requirement_ids}], total_hours, assumptions:[], basis:\"model\"}")
        out, _ = self.ai.generate_json(system, f"REQUIREMENTS:\n{reqs}\n\nPRODUCT FINDINGS:\n{fx}", Estimate, PROMPT_VERSION, 3500)
        out.total_hours = _round(sum(t.hours for t in out.tasks))  # never trust the model's own arithmetic
        out.basis = "model"
        return out
