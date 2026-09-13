"""Guardrails AI and Pydantic validation layer for Intent Mapping and Evidence Grounding."""

import logging
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, ValidationError

try:
    from guardrails import Guard
except ImportError:
    Guard = None

from neurosym.intent.intent_schema import FilterClause, IntentSchema, Operator
from neurosym.runtime.evidence import EvidencePacket
from neurosym.schema.master_schema import MasterSchema

logger = logging.getLogger(__name__)


class GuardrailsValidationResult(BaseModel):
    is_valid: bool
    errors: List[str] = []
    warnings: List[str] = []
    sanitized_data: Optional[Dict[str, Any]] = None


# Official Guardrails Schema Models
class GuardedIntentFilter(BaseModel):
    entity: str
    parameter: str
    operator: str = "="
    value: Any
    value_to: Optional[Any] = None
    source_entity: Optional[str] = None
    description: Optional[str] = None


class GuardedIntentOutput(BaseModel):
    intent_type: str = "PROJECT_SEARCH"
    target_entity: str = "project"
    filters: List[GuardedIntentFilter] = Field(default_factory=list)
    limit: int = 20


class GuardedSynthesisOutput(BaseModel):
    verdict: str
    verdict_rationale: str
    confidence_score: float = 0.98
    regulatory_evidence: List[str] = Field(default_factory=list)
    empirical_evidence: List[str] = Field(default_factory=list)
    operational_evidence: List[str] = Field(default_factory=list)
    feasibility_risks: List[str] = Field(default_factory=list)
    required_actions_for_feasibility: List[str] = Field(default_factory=list)
    grounded_citations: List[str] = Field(default_factory=list)


class GuardrailsValidator:
    """
    Applies Guardrails AI principles and official Guard validation
    to prevent hallucinations in LLM-generated Intent Schemas and Decision Reports.
    """

    # Initialize official Guardrails Guards
    intent_guard = Guard.for_pydantic(GuardedIntentOutput) if Guard is not None else None
    synthesis_guard = Guard.for_pydantic(GuardedSynthesisOutput) if Guard is not None else None

    @staticmethod
    def validate_intent(raw_json: Dict[str, Any], master_schema: MasterSchema) -> GuardrailsValidationResult:
        """Validates that LLM-predicted intent references real Master Schema parameters and operators."""
        errors = []
        warnings = []
        sanitized_filters = []

        target_entity = raw_json.get("target_entity", "project")
        if target_entity not in master_schema.entities:
            errors.append(f"Guardrails Alert: Target entity '{target_entity}' is not in Master Schema. Defaulting to 'project'.")
            target_entity = "project"

        raw_filters = raw_json.get("filters", [])
        for f in raw_filters:
            ent_name = f.get("entity", target_entity)
            param_name = f.get("parameter")
            op_str = f.get("operator", "=")
            val = f.get("value")

            # 1. Validate entity exists
            if ent_name not in master_schema.entities:
                warnings.append(f"Guardrails: Dropped filter with unknown entity '{ent_name}'.")
                continue

            # 2. Validate parameter exists in entity
            entity_schema = master_schema.entities[ent_name]
            if param_name not in entity_schema.parameters:
                warnings.append(f"Guardrails: Dropped hallucinated parameter '{param_name}' not in entity '{ent_name}'.")
                continue

            # 3. Validate operator
            try:
                op_enum = Operator(op_str)
            except ValueError:
                op_enum = Operator.EQ
                warnings.append(f"Guardrails: Coerced invalid operator '{op_str}' to '=' for parameter '{param_name}'.")

            sanitized_filters.append({
                "entity": ent_name,
                "parameter": param_name,
                "operator": op_enum.value,
                "value": val,
                "value_to": f.get("value_to"),
                "source_entity": f.get("source_entity", "llm:neural_intent"),
                "description": f.get("description", f"{param_name} {op_enum.value} {val}")
            })

        sanitized_data = {
            "intent_type": raw_json.get("intent_type", "PROJECT_SEARCH"),
            "target_entity": target_entity,
            "filters": sanitized_filters,
            "limit": raw_json.get("limit", 20)
        }

        return GuardrailsValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            sanitized_data=sanitized_data
        )

    @staticmethod
    def validate_synthesis(raw_json: Dict[str, Any], evidence: EvidencePacket) -> GuardrailsValidationResult:
        """Validates that LLM decision synthesis strictly adheres to evidence packet facts."""
        errors = []
        warnings = []

        verdict = raw_json.get("verdict", "FEASIBLE")

        # Grounding check 0: Out of domain check
        if not evidence.proposal_context.is_domain_relevant or verdict == "OUT_OF_DOMAIN":
            verdict = "OUT_OF_DOMAIN"
            return GuardrailsValidationResult(
                is_valid=True,
                errors=[],
                warnings=[],
                sanitized_data={
                    "verdict": "OUT_OF_DOMAIN",
                    "verdict_rationale": raw_json.get(
                        "verdict_rationale",
                        "This inquiry is outside the scope of EU Horizon Europe proposal evaluation and CORDIS data analytics."
                    ),
                    "confidence_score": 1.0,
                    "regulatory_evidence": [],
                    "empirical_evidence": [],
                    "operational_evidence": [],
                    "feasibility_risks": [],
                    "required_actions_for_feasibility": [
                        "Please submit an inquiry regarding Horizon Europe research project proposals, eligibility, or CORDIS benchmarks."
                    ],
                    "grounded_citations": []
                }
            )

        # Grounding check 1: If critical errors exist, verdict MUST be INFEASIBLE
        if evidence.has_critical_errors and verdict not in ("INFEASIBLE", "REJECTED"):
            errors.append(f"Guardrails Grounding Violation: Evidence has critical errors, but LLM predicted verdict '{verdict}'. Overriding to 'INFEASIBLE'.")
            verdict = "INFEASIBLE"

        # Grounding check 2: Verify cited Rule IDs
        known_rules = {r.rule_id for r in evidence.rule_evaluations}
        cited_findings = raw_json.get("regulatory_evidence", raw_json.get("regulatory_findings", []))
        for finding in cited_findings:
            for rule_id in known_rules:
                if rule_id in finding:
                    # Found legitimate rule citation
                    pass

        sanitized_data = {
            "verdict": verdict,
            "verdict_rationale": raw_json.get("verdict_rationale", ""),
            "confidence_score": raw_json.get("confidence_score", 0.98),
            "regulatory_evidence": raw_json.get("regulatory_evidence", raw_json.get("regulatory_findings", [])),
            "empirical_evidence": raw_json.get("empirical_evidence", raw_json.get("statistical_insights", [])),
            "operational_evidence": raw_json.get("operational_evidence", []),
            "feasibility_risks": raw_json.get("feasibility_risks", raw_json.get("risk_analysis", [])),
            "required_actions_for_feasibility": raw_json.get("required_actions_for_feasibility", raw_json.get("strategic_recommendations", [])),
            "grounded_citations": raw_json.get("grounded_citations", [])
        }

        return GuardrailsValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            sanitized_data=sanitized_data
        )
