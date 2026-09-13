"""Multi-Turn Conversational Chat Agent for Specialized Horizon Europe Proposal Advisory."""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import jinja2

from neurosym.chat.models import ChatMessage, ChatResponse, ChatSession
from neurosym.duckling.client import DucklingClient
from neurosym.guardrails.validators import GuardrailsValidator
from neurosym.ingestion.cordis_ingest import DEFAULT_DB_PATH
from neurosym.llm.client import LLMClient
from neurosym.rules.evaluator import RuleEvaluator
from neurosym.rules.models import FeasibilityVerdict, ProposalContext
from neurosym.runtime.evidence import EvidencePacket, EvidenceRuntime
from neurosym.synthesizer.engine import DecisionSynthesizer

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


class NeuroSymChatAgent:
    """
    Conversational AI Agent providing interactive, multi-turn feasibility advisory
    grounded in official Horizon Europe regulations and CORDIS empirical benchmarks.
    """

    def __init__(self, db_path: Path = DEFAULT_DB_PATH, llm_client: Optional[LLMClient] = None):
        self.db_path = Path(db_path)
        self.llm = llm_client or LLMClient()
        self.evidence_runtime = EvidenceRuntime(db_path=self.db_path)
        self.rule_evaluator = RuleEvaluator(db_path=self.db_path)
        self.deterministic_synthesizer = DecisionSynthesizer()
        self.sessions: Dict[str, ChatSession] = {}
        
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=False
        )

    def get_or_create_session(self, session_id: Optional[str] = None) -> ChatSession:
        """Retrieves existing session or initializes a fresh one."""
        sid = session_id or str(uuid.uuid4())
        if sid not in self.sessions:
            self.sessions[sid] = ChatSession(
                session_id=sid,
                messages=[],
                proposal_context=ProposalContext(raw_prompt="")
            )
        return self.sessions[sid]

    def reset_session(self, session_id: str) -> ChatSession:
        """Resets conversation history and accumulated proposal context for a session."""
        session = ChatSession(
            session_id=session_id,
            messages=[],
            proposal_context=ProposalContext(raw_prompt="")
        )
        self.sessions[session_id] = session
        return session

    def process_message(self, user_message: str, session_id: Optional[str] = None) -> ChatResponse:
        """Processes an incoming user message within a multi-turn conversation."""
        session = self.get_or_create_session(session_id)
        session.updated_at = datetime.now(timezone.utc).isoformat()

        # Record user message
        session.messages.append(ChatMessage(role="user", content=user_message))

        # 1. Extract context from current turn
        turn_context = self.rule_evaluator.extract_context(user_message)

        # 2. Check if whole session or current turn is out of domain
        has_prior_domain_context = (
            session.proposal_context.is_domain_relevant and 
            (session.proposal_context.partner_count is not None or 
             len(session.proposal_context.countries) > 0 or 
             session.proposal_context.domain_topic is not None or
             session.proposal_context.funding_scheme is not None)
        )

        if not turn_context.is_domain_relevant and not has_prior_domain_context:
            # Entirely out of domain
            reply = (
                "I am the specialized NeuroSym Horizon Europe Advisory Agent. "
                "I assist exclusively with EU Horizon Europe proposal feasibility, "
                "consortium structure pre-checks (General Annex B rules), and CORDIS empirical benchmarks. "
                "How can I assist you with your EU research and innovation proposal or consortium structure?"
            )
            session.messages.append(ChatMessage(role="assistant", content=reply))
            return ChatResponse(
                session_id=session.session_id,
                reply=reply,
                verdict=FeasibilityVerdict.OUT_OF_DOMAIN,
                proposal_context=session.proposal_context,
                suggested_followups=[
                    "What are the core eligibility rules for a Horizon Europe RIA project?",
                    "Evaluate our 36-month AI robotics proposal with 4 EU partners",
                    "What is the average grant budget for climate tech in CORDIS?"
                ]
            )

        # 3. Accumulate / merge proposal context across turns
        self._accumulate_proposal_context(session.proposal_context, turn_context)

        # 4. Gather live evidence based on updated accumulated context
        # Construct synthesis prompt representation of the updated context
        summary_prompt = self._build_context_summary_prompt(session.proposal_context)
        evidence = self.evidence_runtime.gather_evidence(summary_prompt)
        
        # Override evidence proposal context with our accumulated context
        evidence.proposal_context = session.proposal_context
        session.latest_evidence = evidence

        # 5. Generate deterministic baseline report
        base_report = self.deterministic_synthesizer.synthesize(evidence)
        session.latest_verdict = base_report.verdict

        # 6. Render Conversational Jinja2 prompt
        template = self.jinja_env.get_template("chat_advisor_prompt.j2")
        rendered_prompt = template.render(
            conversation_history=[m.model_dump() for m in session.messages[-8:]],
            user_message=user_message,
            proposal_context=session.proposal_context,
            evidence=evidence,
            base_report=base_report
        )

        # 7. Call LLM for conversational reasoning
        raw_llm_output = self.llm.generate_json(rendered_prompt)
        
        reply_text = raw_llm_output.get("reply") if isinstance(raw_llm_output, dict) else None
        if not reply_text:
            # Fallback to high quality deterministic narrative
            reply_text = (
                f"### {base_report.verdict.value}\n\n"
                f"{base_report.verdict_rationale}\n\n"
            )
            if base_report.regulatory_evidence:
                reply_text += "**Regulatory Assessment:**\n" + "\n".join([f"- {r}" for r in base_report.regulatory_evidence]) + "\n\n"
            if base_report.empirical_evidence:
                reply_text += "**Empirical CORDIS Benchmarks:**\n" + "\n".join([f"- {e}" for e in base_report.empirical_evidence]) + "\n\n"
            if base_report.required_actions_for_feasibility:
                reply_text += "**Actionable Next Steps:**\n" + "\n".join([f"- {a}" for a in base_report.required_actions_for_feasibility])

        suggested_followups = raw_llm_output.get("suggested_followups", []) if isinstance(raw_llm_output, dict) else []
        if not suggested_followups:
            if base_report.verdict == FeasibilityVerdict.INFEASIBLE:
                suggested_followups = [
                    "How can we fix our consortium structure to meet General Annex B?",
                    "Which countries should we add to become eligible?"
                ]
            else:
                suggested_followups = [
                    "What is the recommended budget band for our consortium size?",
                    "How does our 36-month timeline compare to historical projects?"
                ]

        # Neuro-symbolic supremacy: enforce deterministic statutory verdict
        final_verdict = base_report.verdict
        if final_verdict == FeasibilityVerdict.INFEASIBLE and "INFEASIBLE" not in (reply_text or "").upper():
            reply_text = (
                f"### Statutory Infeasibility Alert: INFEASIBLE\n\n"
                f"{base_report.verdict_rationale}\n\n"
                f"{reply_text or ''}"
            )

        # Record assistant reply
        session.messages.append(ChatMessage(
            role="assistant",
            content=reply_text,
            metadata={"verdict": final_verdict.value}
        ))

        return ChatResponse(
            session_id=session.session_id,
            reply=reply_text,
            verdict=final_verdict,
            proposal_context=session.proposal_context,
            regulatory_evidence=base_report.regulatory_evidence,
            empirical_evidence=base_report.empirical_evidence,
            operational_evidence=base_report.operational_evidence,
            feasibility_risks=base_report.feasibility_risks,
            required_actions=base_report.required_actions_for_feasibility,
            suggested_followups=suggested_followups,
            domain_statistics=evidence.domain_statistics,
            comparable_projects=evidence.comparable_projects,
            is_grounded=base_report.is_grounded
        )

    def _accumulate_proposal_context(self, current: ProposalContext, turn: ProposalContext):
        """Merges incremental state changes into the active session ProposalContext."""
        if turn.funding_scheme:
            current.funding_scheme = turn.funding_scheme
        if turn.domain_topic:
            current.domain_topic = turn.domain_topic
        if turn.our_role:
            current.our_role = turn.our_role
        if turn.requested_duration_months:
            current.requested_duration_months = turn.requested_duration_months
        if turn.requested_budget_eur:
            current.requested_budget_eur = turn.requested_budget_eur
        
        # Merge countries
        if turn.countries:
            merged_countries = sorted(list(set(current.countries + turn.countries)))
            current.countries = merged_countries
            eu27 = set(self.rule_evaluator.named_sets.get("EU27", []))
            associated = set(self.rule_evaluator.named_sets.get("ASSOCIATED", []))
            current.distinct_country_count = len(merged_countries)
            current.member_state_count = sum(1 for c in merged_countries if c in eu27)
            current.associated_country_count = sum(1 for c in merged_countries if c in associated)
            current.third_country_count = sum(1 for c in merged_countries if c not in eu27 and c not in associated)

        prev_countries = set(current.countries) - set(turn.countries)
        if turn.partner_count:
            current.partner_count = turn.partner_count
        elif turn.countries and prev_countries:
            new_countries_count = len(set(turn.countries) - prev_countries)
            if new_countries_count > 0:
                current.partner_count = max((current.partner_count or 0) + new_countries_count, len(current.countries))
            else:
                current.partner_count = max(current.partner_count or 0, len(current.countries))
        else:
            current.partner_count = max(current.partner_count or 0, len(current.countries))

        current.is_domain_relevant = True

    def _build_context_summary_prompt(self, p: ProposalContext) -> str:
        """Synthesizes a declarative prompt from accumulated ProposalContext."""
        parts = []
        if p.partner_count:
            parts.append(f"Consortium of {p.partner_count} partners")
        if p.countries:
            parts.append(f"across {', '.join(p.countries)}")
        if p.requested_duration_months:
            parts.append(f"for {p.requested_duration_months} months")
        if p.funding_scheme:
            parts.append(f"under {p.funding_scheme}")
        if p.domain_topic:
            parts.append(f"working on {p.domain_topic}")
        if p.requested_budget_eur:
            parts.append(f"with budget €{p.requested_budget_eur:,.0f}")
        
        return " ".join(parts) if parts else "Horizon Europe project proposal"
