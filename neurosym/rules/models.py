"""Pydantic models for Horizon Europe decision rules, proposal feasibility evaluations, and empirical benchmarks."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class RuleSource(str, Enum):
    OFFICIAL = "official"
    BENCHMARK = "benchmark"
    POLICY = "policy"


class RuleStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class AppliesWhen(BaseModel):
    field: str
    op: str
    value: Any


class Rule(BaseModel):
    rule_id: str
    source: RuleSource
    name: str
    field: str
    op: str
    value: Any
    severity: Severity = Severity.ERROR
    applies_when: Optional[AppliesWhen] = None
    message: str
    reference: str
    evidence: Optional[str] = None


class RuleEvaluation(BaseModel):
    rule_id: str
    name: str
    source: RuleSource
    severity: Severity
    status: RuleStatus
    field: str
    actual_value: Any = None
    required_condition: str
    message: str
    reference: str
    evidence_details: Optional[Dict[str, Any]] = None


class ProposalContext(BaseModel):
    raw_prompt: str
    is_domain_relevant: bool = True
    out_of_domain_reason: Optional[str] = None
    partner_count: Optional[int] = None
    countries: List[str] = Field(default_factory=list)
    distinct_country_count: int = 0
    member_state_count: int = 0
    associated_country_count: int = 0
    third_country_count: int = 0
    funding_scheme: Optional[str] = None
    requested_budget_eur: Optional[float] = None
    requested_duration_months: Optional[int] = None
    our_role: Optional[str] = None
    domain_topic: Optional[str] = None


class DomainStatistics(BaseModel):
    comparable_project_count: int = 0
    funding_scheme: Optional[str] = None
    topic: Optional[str] = None
    budget_p5: float = 0.0
    budget_p25: float = 0.0
    budget_p50: float = 0.0
    budget_p75: float = 0.0
    budget_p95: float = 0.0
    budget_p98: float = 0.0
    budget_mean: float = 0.0
    requested_budget_percentile: Optional[float] = None
    avg_partner_count: float = 0.0
    median_partner_count: float = 0.0
    avg_duration_months: float = 0.0


class FeasibilityVerdict(str, Enum):
    FEASIBLE = "FEASIBLE"
    CONDITIONALLY_FEASIBLE = "CONDITIONALLY FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"


class EvaluationReport(BaseModel):
    verdict: FeasibilityVerdict = FeasibilityVerdict.FEASIBLE
    summary: str
    proposal: ProposalContext
    statistics: Optional[DomainStatistics] = None
    evaluations: List[RuleEvaluation] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
