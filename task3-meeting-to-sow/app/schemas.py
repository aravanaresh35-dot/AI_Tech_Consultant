"""Versioned structured contracts between agents. Bump SCHEMA_VERSION when a field changes."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION = "sow-v1"
PROMPT_VERSION = "sow-prompts-v1"


class Requirement(BaseModel):
    id: str
    text: str
    type: Literal["functional", "integration", "design", "content", "data", "reporting", "other"] = "functional"
    priority: Literal["must", "should", "could", "unspecified"] = "unspecified"
    status: Literal["in_scope", "out_of_scope", "removed"] = "in_scope"
    source_quote: str = ""
    change_hint: Optional[Literal["added", "modified", "removed", "unchanged"]] = None
    ambiguous: bool = False
    ambiguity_reason: str = ""


class AnalystOutput(BaseModel):
    input_status: Literal["ok", "insufficient", "possibly_truncated"] = "ok"
    requirements: list[Requirement] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    acceptance_criteria: dict[str, list[str]] = Field(default_factory=dict)  # requirement id -> criteria stated in meeting
    warnings: list[str] = Field(default_factory=list)
    objective_hint: str = ""
    mode: str = "demo"


class EvidenceItem(BaseModel):
    title: str
    url: str
    snippet: str


class KBFinding(BaseModel):
    requirement_id: str
    query: str
    evidence_status: Literal["supported", "partial", "insufficient", "unavailable"]
    existing_feature_candidate: bool
    custom_development_likely: Optional[bool]  # None = cannot tell (KB unavailable)
    confidence: float
    evidence: list[EvidenceItem] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    statement: str


class EstimateTask(BaseModel):
    id: str
    name: str
    description: str
    hours: float = Field(ge=0)
    reasoning: str
    dependencies: list[str] = Field(default_factory=list)
    risk: Literal["low", "medium", "high"] = "medium"
    requirement_ids: list[str] = Field(default_factory=list)


class Estimate(BaseModel):
    tasks: list[EstimateTask]
    total_hours: float
    assumptions: list[str]
    basis: str  # "heuristic_demo" | "model"


class Scope(BaseModel):
    objective: str
    requirements: list[Requirement]
    in_scope: list[str]
    out_of_scope: list[str]
    assumptions: list[str]
    dependencies: list[str]
    acceptance_criteria: list[str]
    open_questions: list[str]


class Commercial(BaseModel):
    status: Literal["not_configured", "illustrative"]
    hourly_rate: Optional[float] = None
    currency: str = "USD"
    amount: Optional[float] = None
    label: str


class Proposal(BaseModel):
    executive_summary: str
    client_requirements: list[str]
    proposed_solution: str
    deliverables: list[str]
    timeline: dict
    commercial: Commercial
    exclusions: list[str]
    risks_and_assumptions: list[str]
    approval: dict


class Issue(BaseModel):
    severity: Literal["error", "warning"]
    message: str


class ValidationReport(BaseModel):
    passed: bool
    issues: list[Issue]


class Comparison(BaseModel):
    from_version: int
    to_version: int
    unchanged: list[str]
    modified: list[dict]
    added: list[str]
    removed: list[str]
    out_of_scope_changes: list[str]
    previous_total_hours: float
    new_total_hours: float
    additional_hours: float
    requires_client_approval: list[str]
