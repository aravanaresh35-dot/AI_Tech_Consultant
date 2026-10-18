"""Sequential workflow: Analyst -> Product Consultant (Knowledge Brain) -> Estimator -> Scope -> Proposal -> Validator.

Sequential on purpose: each step has a typed input/output contract and is easy to explain and test.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from tech_common.ai import AIClient
from tech_common.kb_client import KnowledgeBrainClient
from tech_common.logging_setup import log

from .analyst import TranscriptAnalyst
from .comparison import compare
from .config import Settings
from .consultant import ProductConsultant
from .estimator import EstimationAgent
from .proposal import ProposalAgent, Validator, build_scope
from .schemas import PROMPT_VERSION, SCHEMA_VERSION, AnalystOutput, Estimate, Requirement

logger = logging.getLogger("pipeline")


class Pipeline:
    def __init__(self, ai: AIClient, kb: KnowledgeBrainClient, s: Settings):
        self.ai, self.s = ai, s
        self.analyst = TranscriptAnalyst(ai, s.min_transcript_chars)
        self.consultant = ProductConsultant(kb, s.kb_top_k)
        self.estimator = EstimationAgent(ai)
        self.proposer = ProposalAgent(s.hourly_rate, s.currency, s.team_hours_per_week)
        self.validator = Validator()

    def run(self, client: str, transcript: str, version: int, prev: Optional[dict] = None) -> dict:
        timings: dict[str, float] = {}

        def timed(name, fn, *a):
            t0 = time.perf_counter()
            r = fn(*a)
            timings[name] = round((time.perf_counter() - t0) * 1000, 1)
            return r

        prev_reqs = [Requirement(**r) for r in prev["scope"]["requirements"]] if prev else None
        a: AnalystOutput = timed("transcript_analyst", self.analyst.run, transcript, prev_reqs)
        reqs = self._merge(prev_reqs, a.requirements) if prev_reqs is not None else a.requirements
        if prev and a.input_status == "insufficient":
            reqs = prev_reqs  # nothing usable in the follow-up: keep the previous requirements unchanged
        findings = timed("product_consultant", self.consultant.run, reqs)
        estimate: Estimate = timed("estimation_agent", self.estimator.run, reqs, findings)
        scope = build_scope(a, reqs, findings, estimate)
        proposal = timed("proposal_agent", self.proposer.run, client, scope, estimate, findings, version)
        validation = timed("validation", self.validator.run, a, scope, estimate, findings, proposal, self.s.hourly_rate is not None)
        comparison = None
        if prev:
            comparison = compare(prev_reqs or [], reqs, Estimate(**prev["estimate"]), estimate, version - 1, version).model_dump()
        bundle = {
            "schema_version": SCHEMA_VERSION, "prompt_version": PROMPT_VERSION,
            "analysis": a.model_dump(), "findings": [f.model_dump() for f in findings], "estimate": estimate.model_dump(),
            "scope": scope.model_dump(), "proposal": proposal.model_dump(), "validation": validation.model_dump(),
            "comparison": comparison,
            "meta": {"mode": self.ai.mode, "model": self.ai.model if self.ai.is_live else None, "timings_ms": timings,
                     "estimate_basis": estimate.basis, "analysis_mode": a.mode},
        }
        log(logger, "pipeline_done", version=version, requirements=len(reqs), hours=estimate.total_hours, valid=validation.passed)
        return bundle

    @staticmethod
    def _merge(prev: list[Requirement], found: list[Requirement]) -> list[Requirement]:
        merged = {r.id: r.model_copy() for r in prev}
        for f in found:
            if f.change_hint == "unchanged" and f.id in merged:
                continue
            if f.id in merged:
                p = merged[f.id]
                if f.change_hint == "removed":
                    p.status = "removed"
                else:
                    p.text, p.type, p.priority, p.status = f.text, f.type, f.priority, f.status
                    p.ambiguous, p.ambiguity_reason, p.source_quote = f.ambiguous, f.ambiguity_reason, f.source_quote
                p.change_hint = f.change_hint
            else:
                merged[f.id] = f
        return list(merged.values())
