"""Regulated Decision Synthesizer formulating evidence-grounded feasibility verdicts."""

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from neurosym.rules.models import FeasibilityVerdict, RuleStatus, Severity
from neurosym.runtime.evidence import EvidencePacket
from neurosym.synthesizer.grounding import GroundingValidator

logger = logging.getLogger(__name__)


class SynthesizedReport(BaseModel):
    """Authoritative feasibility evaluation report strictly grounded on evidence."""
    verdict: FeasibilityVerdict
    verdict_rationale: str
    confidence_score: float = 1.0
    
    # 3-Dimensional Evidence Breakdown
    regulatory_evidence: List[str] = Field(default_factory=list)
    empirical_evidence: List[str] = Field(default_factory=list)
    operational_evidence: List[str] = Field(default_factory=list)
    
    # Feasibility Risks & Required Actions
    feasibility_risks: List[str] = Field(default_factory=list)
    required_actions_for_feasibility: List[str] = Field(default_factory=list)
    
    # Grounded Citations & References
    grounded_citations: List[str] = Field(default_factory=list)
    evidence_summary: Dict[str, Any] = Field(default_factory=dict)
    
    # Audit Validation
    is_grounded: bool = True
    grounding_audit_notes: List[str] = Field(default_factory=list)


class DecisionSynthesizer:
    """
    Synthesizes a multi-dimensional Feasibility Verdict and advisory report from an EvidencePacket
    under strict anti-hallucination and evidence-grounding constraints.
    """

    def __init__(self, grounding_validator: Optional[GroundingValidator] = None):
        self.validator = grounding_validator or GroundingValidator()

    def synthesize(self, evidence: EvidencePacket) -> SynthesizedReport:
        """Processes EvidencePacket and produces a grounded feasibility report."""
        p = evidence.proposal_context
        stats = evidence.domain_statistics
        rule_evals = evidence.rule_evaluations

        # If prompt is out of domain, politely reject answering
        if not p.is_domain_relevant:
            return SynthesizedReport(
                verdict=FeasibilityVerdict.OUT_OF_DOMAIN,
                verdict_rationale=(
                    "This inquiry is outside the domain scope of the NeuroSym Feasibility Engine. "
                    "I am specialized exclusively in assessing EU Horizon Europe proposal feasibility, "
                    "regulatory compliance (such as General Annex B eligibility rules), and CORDIS empirical benchmarks. "
                    "Please provide a prompt related to Horizon Europe research proposals, consortium structures, or EU funding calls."
                ),
                confidence_score=1.0,
                regulatory_evidence=[],
                empirical_evidence=[],
                operational_evidence=[],
                feasibility_risks=[],
                required_actions_for_feasibility=[
                    "Submit an inquiry containing a Horizon Europe project concept, consortium structure, or funding scheme."
                ],
                grounded_citations=[],
                evidence_summary={"is_domain_relevant": False},
                is_grounded=True,
                grounding_audit_notes=[]
            )

        regulatory_evidence: List[str] = []
        empirical_evidence: List[str] = []
        operational_evidence: List[str] = []
        feasibility_risks: List[str] = []
        required_actions: List[str] = []
        citations: List[str] = []

        failed_critical_rules = [r for r in rule_evals if r.status == RuleStatus.FAILED and r.severity == Severity.ERROR]
        failed_warnings = [r for r in rule_evals if r.status == RuleStatus.FAILED and r.severity == Severity.WARNING]

        # 1. Dimension 1: Regulatory & Legal Feasibility Evidence
        for r in rule_evals:
            if r.status == RuleStatus.FAILED:
                prefix = "[VIOLATION]" if r.severity == Severity.ERROR else "[CAUTION]"
                regulatory_evidence.append(f"{prefix} {r.rule_id} ({r.name}): {r.message} [Ref: {r.reference}]")
                citations.append(f"{r.rule_id}: {r.reference}")
            elif r.status == RuleStatus.PASSED:
                regulatory_evidence.append(f"[COMPLIANT] {r.rule_id} ({r.name}): Satisfied ({r.field} = {r.actual_value}).")

        # 2. Dimension 2: Empirical & Financial Feasibility Evidence (Live DuckDB)
        if stats and stats.comparable_project_count > 0:
            empirical_evidence.append(
                f"Historical Cohort: Benchmark derived from {stats.comparable_project_count:,} funded {stats.funding_scheme} projects in CORDIS."
            )
            empirical_evidence.append(
                f"Budget Benchmark Band: 5th percentile = €{stats.budget_p5:,.2f} | Median (P50) = €{stats.budget_p50:,.2f} | 95th percentile = €{stats.budget_p95:,.2f}."
            )
            
            if stats.requested_budget_percentile is not None:
                rank = stats.requested_budget_percentile
                if rank > 95:
                    empirical_evidence.append(
                        f"Budget Outlier: Requested funding of €{p.requested_budget_eur:,.2f} is at the {rank}th percentile (exceeds 95th percentile threshold of €{stats.budget_p95:,.2f})."
                    )
                    feasibility_risks.append(
                        f"Financial Feasibility Risk: Budget exceeds 95th percentile of historical grants. Evaluators may cut budget or question cost realism."
                    )
                elif rank < 5:
                    empirical_evidence.append(
                        f"Budget Outlier: Requested funding is at the {rank}th percentile (below 5th percentile baseline of €{stats.budget_p5:,.2f})."
                    )
                    feasibility_risks.append(
                        "Under-budgeting Risk: Proposed grant may be insufficient to deliver full RIA scope."
                    )
                else:
                    empirical_evidence.append(
                        f"Budget Feasibility: Requested funding falls within normal historical range ({rank}th percentile)."
                    )

        # 3. Dimension 3: Operational & Consortium Feasibility Evidence
        if stats and stats.median_partner_count > 0:
            operational_evidence.append(
                f"Consortium Density: Historical median is {stats.median_partner_count} partners (mean: {stats.avg_partner_count})."
            )
            operational_evidence.append(
                f"Project Timeline: Historical average duration is {stats.avg_duration_months:.1f} months."
            )

            if p.partner_count is not None and p.partner_count < stats.median_partner_count * 0.5:
                feasibility_risks.append(
                    f"Consortium Capacity Risk: Proposed {p.partner_count} partners is significantly below historical median ({stats.median_partner_count} partners). Reviewers may doubt operational bandwidth across diverse work packages."
                )

        if p.requested_duration_months is not None and p.requested_duration_months > 48:
            feasibility_risks.append(
                f"Timeline Infeasibility: Proposed duration of {p.requested_duration_months} months exceeds the 48-month statutory cap."
            )

        if p.third_country_count > 0:
            feasibility_risks.append(
                f"Third-Country Funding Risk: {p.third_country_count} non-associated third-country partner(s) detected. Confirm co-funding mechanisms."
            )

        # 4. Required Actions to Achieve / Maintain Feasibility
        if failed_critical_rules:
            for fr in failed_critical_rules:
                if fr.rule_id == "R-001":
                    required_actions.append("Add independent legal entities from eligible countries to meet minimum legal threshold of 3.")
                elif fr.rule_id == "R-002":
                    required_actions.append("Broaden consortium to include partners from at least 3 distinct Member States or Associated Countries.")
                elif fr.rule_id == "R-003":
                    required_actions.append("Ensure at least one consortium partner is established in an EU27 Member State.")
                elif fr.rule_id == "R-008":
                    required_actions.append(f"Compress work plan from {p.requested_duration_months} months to 48 months or fewer.")
                elif fr.rule_id == "P-001":
                    required_actions.append("Increase requested EU contribution to at least €2.0M to coordinate under internal policy.")
        else:
            if p.partner_count is not None and p.partner_count <= 5:
                required_actions.append(
                    "Work Package Distribution: Ensure the 4 partners explicitly cover Core R&D, Industrial Pilot Validation, and Dissemination/Exploitation to mitigate the small-consortium risk."
                )
            if stats and stats.budget_p50 > 0 and p.requested_budget_eur is None:
                required_actions.append(
                    f"Budget Calibration: Recommended target budget is €{stats.budget_p50 * 0.6:,.0f} – €{stats.budget_p50:,.0f} for this consortium scale."
                )

        # 5. Formulate Feasibility Verdict
        if failed_critical_rules:
            verdict = FeasibilityVerdict.INFEASIBLE
            verdict_rationale = (
                f"The proposal is INFEASIBLE in its current structure due to {len(failed_critical_rules)} "
                f"fatal regulatory / eligibility violation(s): {', '.join([r.rule_id for r in failed_critical_rules])}."
            )
            confidence = 1.0
        elif failed_warnings or feasibility_risks:
            verdict = FeasibilityVerdict.CONDITIONALLY_FEASIBLE
            verdict_rationale = (
                f"The proposal is CONDITIONALLY FEASIBLE. It satisfies statutory eligibility, but presents "
                f"{len(feasibility_risks)} operational / empirical risk(s) that require mitigation."
            )
            confidence = 0.95
        else:
            verdict = FeasibilityVerdict.FEASIBLE
            verdict_rationale = (
                "The proposal is FEASIBLE. It satisfies all core Horizon Europe eligibility rules, statutory "
                "duration caps, and aligns with historical CORDIS benchmarks."
            )
            confidence = 0.98

        # Citations
        for proj in evidence.comparable_projects[:3]:
            citations.append(f"CORDIS Project {proj.get('acronym')} (ID: {proj.get('id')}) - Budget €{proj.get('totalCost', 0):,.2f}")

        # Summary dict
        evidence_summary = {
            "partner_count": p.partner_count,
            "countries": p.countries,
            "duration_months": p.requested_duration_months,
            "requested_budget_eur": p.requested_budget_eur,
            "funding_scheme": p.funding_scheme,
            "comparable_projects_analyzed": stats.comparable_project_count if stats else 0,
            "rules_evaluated_count": len(rule_evals),
            "critical_violations_count": len(failed_critical_rules),
            "warnings_count": len(failed_warnings),
            "feasibility_risks_count": len(feasibility_risks)
        }

        report_text = f"{verdict.value} {verdict_rationale} {' '.join(regulatory_evidence)}"
        is_grounded, audit_notes = self.validator.validate(report_text, evidence)

        return SynthesizedReport(
            verdict=verdict,
            verdict_rationale=verdict_rationale,
            confidence_score=confidence,
            regulatory_evidence=regulatory_evidence,
            empirical_evidence=empirical_evidence,
            operational_evidence=operational_evidence,
            feasibility_risks=feasibility_risks,
            required_actions_for_feasibility=required_actions,
            grounded_citations=citations,
            evidence_summary=evidence_summary,
            is_grounded=is_grounded,
            grounding_audit_notes=audit_notes
        )
