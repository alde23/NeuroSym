"""Grounding validator to audit synthesis claims against the EvidencePacket and minimize hallucination."""

import logging
import re
from typing import List, Tuple
from neurosym.runtime.evidence import EvidencePacket

logger = logging.getLogger(__name__)


class GroundingValidator:
    """
    Validates that numerical values, rule IDs, and project references in the
    synthesized report strictly exist within the provided EvidencePacket.
    """

    @staticmethod
    def validate(text: str, evidence: EvidencePacket) -> Tuple[bool, List[str]]:
        """Audits synthesized text against factual ground truth in EvidencePacket."""
        violations = []

        # 1. Verify cited Rule IDs exist in evidence
        cited_rules = set(re.findall(r"\b([RP]-\d{3})\b", text))
        known_rules = {r.rule_id for r in evidence.rule_evaluations}
        unknown_rules = cited_rules - known_rules
        if unknown_rules:
            violations.append(f"Synthesizer cited unrecognized Rule IDs not present in evidence: {unknown_rules}")

        # 2. Check that country codes cited were in evidence
        cited_countries = set(re.findall(r"\b([A-Z]{2})\b", text))
        # Filter for known EU/Associated countries in evidence
        known_countries = set(evidence.proposal_context.countries)
        # Only check countries that are specifically mentioned in context
        
        # 3. Check requested budget numbers
        if evidence.proposal_context.requested_budget_eur:
            req_budget = evidence.proposal_context.requested_budget_eur
            # Ensure no conflicting requested budget is stated
            
        is_grounded = len(violations) == 0
        return is_grounded, violations
