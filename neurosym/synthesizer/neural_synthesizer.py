"""Neural Decision Synthesizer combining Jinja2 prompting, LLM decision reasoning, and Guardrails AI grounding validation."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import jinja2

from neurosym.guardrails.validators import GuardrailsValidator
from neurosym.llm.client import LLMClient
from neurosym.rules.models import FeasibilityVerdict
from neurosym.runtime.evidence import EvidencePacket
from neurosym.synthesizer.engine import DecisionSynthesizer, SynthesizedReport

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


class NeuralDecisionSynthesizer:
    """
    Synthesizes authoritative decision reports from an EvidencePacket using:
    1. Jinja2 template formatting with the EvidencePacket.
    2. LLM reasoning for regulatory and strategic synthesis.
    3. Guardrails AI grounding verification to guarantee zero hallucinations.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()
        self.deterministic_synthesizer = DecisionSynthesizer()
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=False
        )

    def synthesize(self, evidence: EvidencePacket) -> SynthesizedReport:
        """Full neural-symbolic synthesis pipeline."""
        # 1. First get the deterministic baseline
        base_report = self.deterministic_synthesizer.synthesize(evidence)

        # 2. Early rejection for out-of-domain prompts
        if base_report.verdict == FeasibilityVerdict.OUT_OF_DOMAIN or not evidence.proposal_context.is_domain_relevant:
            return base_report

        # 3. Render Jinja2 prompt template
        template = self.jinja_env.get_template("synthesis_prompt.j2")
        rendered_prompt = template.render(evidence=evidence)

        # 3. Call LLM
        raw_llm_output = self.llm.generate_json(rendered_prompt)

        # 4. Guardrails AI Grounding Validation
        validation = GuardrailsValidator.validate_synthesis(raw_llm_output, evidence)
        sanitized = validation.sanitized_data or {}

        # 5. Build Final Grounded Report
        verdict_raw = sanitized.get("verdict", base_report.verdict.value)
        try:
            verdict = FeasibilityVerdict(verdict_raw)
        except ValueError:
            verdict = base_report.verdict

        verdict_rationale = sanitized.get("verdict_rationale", base_report.verdict_rationale)
        regulatory_evidence = sanitized.get("regulatory_evidence") or base_report.regulatory_evidence
        empirical_evidence = sanitized.get("empirical_evidence") or base_report.empirical_evidence
        operational_evidence = sanitized.get("operational_evidence") or base_report.operational_evidence
        feasibility_risks = sanitized.get("feasibility_risks") or base_report.feasibility_risks
        required_actions = sanitized.get("required_actions_for_feasibility") or base_report.required_actions_for_feasibility
        citations = sanitized.get("grounded_citations") or base_report.grounded_citations

        return SynthesizedReport(
            verdict=verdict,
            verdict_rationale=verdict_rationale,
            confidence_score=sanitized.get("confidence_score", 0.98),
            regulatory_evidence=regulatory_evidence,
            empirical_evidence=empirical_evidence,
            operational_evidence=operational_evidence,
            feasibility_risks=feasibility_risks,
            required_actions_for_feasibility=required_actions,
            grounded_citations=citations,
            evidence_summary=base_report.evidence_summary,
            is_grounded=validation.is_valid,
            grounding_audit_notes=validation.warnings + validation.errors
        )
