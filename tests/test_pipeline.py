"""Comprehensive end-to-end tests for NeuroSym Duckling, DuckDB, Jinja2, LLM, and Guardrails AI."""

import pytest
from pathlib import Path
from neurosym.duckling.client import DucklingClient
from neurosym.guardrails.validators import GuardrailsValidator
from neurosym.ingestion.cordis_ingest import DEFAULT_DB_PATH, DEFAULT_SCHEMA_PATH
from neurosym.intent.intent_schema import Operator
from neurosym.intent.mapper import IntentMapper
from neurosym.intent.neural_mapper import NeuralIntentMapper
from neurosym.llm.client import LLMClient
from neurosym.query.engine import QueryEngine
from neurosym.rules.evaluator import RuleEvaluator
from neurosym.rules.models import FeasibilityVerdict, Severity, RuleStatus
from neurosym.runtime.evidence import EvidenceRuntime
from neurosym.schema.master_schema import MasterSchema
from neurosym.synthesizer.neural_synthesizer import NeuralDecisionSynthesizer


def test_duckling_live_container():
    """Verify Duckling container on port 8005 extracts entities accurately."""
    client = DucklingClient(endpoint_url="http://localhost:8005/parse")
    entities = client.extract_entities("Find projects starting after Jan 2023 with budget over 2 million EUR")
    
    dims = [e.dim for e in entities]
    assert "time" in dims, "Duckling should extract 'time' dimension"
    assert "amount-of-money" in dims, "Duckling should extract 'amount-of-money' dimension"
    
    amount_ent = next(e for e in entities if e.dim == "amount-of-money")
    assert amount_ent.min_amount == 2000000.0 or amount_ent.num_value == 2000000.0
    assert amount_ent.currency == "EUR"

    time_ent = next(e for e in entities if e.dim == "time")
    assert time_ent.start_date.startswith("2023-01")


def test_guardrails_intent_validation():
    """Verify Guardrails AI intercepts hallucinated columns or invalid operators."""
    schema = MasterSchema()
    # Add dummy entity
    from neurosym.schema.master_schema import EntitySchema, ParameterSchema, SemanticType
    schema.entities["project"] = EntitySchema(
        name="project", table_name="project", description="projects",
        parameters={"totalCost": ParameterSchema(name="totalCost", table="project", column="totalCost", sql_type="DOUBLE", semantic_type=SemanticType.AMOUNT_OF_MONEY, description="budget")}
    )

    bad_intent = {
        "target_entity": "project",
        "filters": [
            {"entity": "project", "parameter": "totalCost", "operator": ">=", "value": 5000000},
            {"entity": "project", "parameter": "hallucinated_column", "operator": "==", "value": "xyz"},
            {"entity": "non_existent_table", "parameter": "abc", "operator": "=", "value": 123}
        ]
    }
    res = GuardrailsValidator.validate_intent(bad_intent, schema)
    assert len(res.sanitized_data["filters"]) == 1
    assert res.sanitized_data["filters"][0]["parameter"] == "totalCost"
    assert len(res.warnings) == 2


def test_neural_intent_mapping():
    """Verify NeuralIntentMapper combines Duckling, Jinja2, and Guardrails."""
    mapper = NeuralIntentMapper()
    intent = mapper.parse_and_map("Find AI projects starting after Jan 2023 in Germany with budget over 5 million EUR")
    
    assert intent.target_entity == "project"
    filter_params = {f.parameter for f in intent.filters}
    assert "startDate" in filter_params
    assert "country" in filter_params
    assert "totalCost" in filter_params or "ecMaxContribution" in filter_params


def test_evidence_runtime_and_neural_synthesis():
    """Verify full pipeline: EvidenceRuntime -> EvidencePacket -> NeuralDecisionSynthesizer."""
    runtime = EvidenceRuntime()
    prompt = "We are forming an international consortium of 4 institutions across Germany, the Netherlands, and Sweden to execute a 36-month Horizon Europe Research and Innovation Action on autonomous robotics for hazardous site remediation."
    
    evidence = runtime.gather_evidence(prompt)
    assert evidence.proposal_context.partner_count == 4
    assert evidence.proposal_context.distinct_country_count == 3
    assert evidence.domain_statistics is not None
    assert evidence.domain_statistics.comparable_project_count > 0

    synthesizer = NeuralDecisionSynthesizer()
    report = synthesizer.synthesize(evidence)
    
    assert report.verdict in ("FEASIBLE", "CONDITIONALLY FEASIBLE", FeasibilityVerdict.FEASIBLE, FeasibilityVerdict.CONDITIONALLY_FEASIBLE)
    assert report.confidence_score >= 0.90
    assert len(report.regulatory_evidence) > 0
    assert len(report.empirical_evidence) > 0
    assert report.is_grounded is True


def test_out_of_domain_rejection():
    """Verify that unrelated prompts are politely rejected as OUT_OF_DOMAIN."""
    runtime = EvidenceRuntime()
    out_of_domain_prompt = "Can you give me a recipe for homemade chocolate fudge brownies?"
    
    evidence = runtime.gather_evidence(out_of_domain_prompt)
    assert evidence.proposal_context.is_domain_relevant is False
    
    synthesizer = NeuralDecisionSynthesizer()
    report = synthesizer.synthesize(evidence)
    
    assert report.verdict in ("OUT_OF_DOMAIN", FeasibilityVerdict.OUT_OF_DOMAIN)
    assert "outside the" in report.verdict_rationale.lower() or "horizon europe" in report.verdict_rationale.lower()
    assert len(report.regulatory_evidence) == 0
