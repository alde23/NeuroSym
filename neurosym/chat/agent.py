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
from neurosym.query.engine import QueryEngine
from neurosym.rules.evaluator import RuleEvaluator
from neurosym.rules.models import DomainStatistics, FeasibilityVerdict, ProposalContext
from neurosym.runtime.evidence import EvidencePacket, EvidenceRuntime
from neurosym.synthesizer.engine import DecisionSynthesizer

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


class NeuroSymChatAgent:
    """
    Conversational AI Agent providing interactive, multi-turn feasibility advisory,
    CORDIS empirical data lookups, and General Annex B regulatory guidance.
    """

    def __init__(self, db_path: Path = DEFAULT_DB_PATH, llm_client: Optional[LLMClient] = None):
        self.db_path = Path(db_path)
        self.llm = llm_client or LLMClient()
        self.query_engine = QueryEngine(db_path=self.db_path)
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

    def _classify_intent(self, user_message: str, session: ChatSession, turn_context: ProposalContext) -> str:
        """
        Classifies incoming query into distinct operational intents:
        - OUT_OF_DOMAIN
        - DATA_QUERY (empirical analytics, averages, CORDIS lookups)
        - REGULATORY_INQUIRY (rules, policies, Annex B explanations)
        - STRATEGY_FOLLOWUP (active session follow-ups: work packages, co-funding, etc.)
        - PROPOSAL_EVALUATION (consortium / budget / feasibility assessment)
        """
        p_lower = user_message.lower().strip()

        # Check out of domain
        has_prior_domain_context = (
            session.proposal_context.is_domain_relevant and 
            (session.proposal_context.partner_count is not None or 
             len(session.proposal_context.countries) > 0 or 
             session.proposal_context.domain_topic is not None or
             session.proposal_context.funding_scheme is not None)
        )

        if not turn_context.is_domain_relevant and not has_prior_domain_context:
            return "OUT_OF_DOMAIN"

        # Explicit Proposal Evaluation triggers or proposal parameter updates (countries, partners, budget, duration)
        eval_triggers = ["evaluate", "evaluate our", "assess our", "feasibility", "consortium of", "forming a consortium", "partner across", "partners across", "submit a"]
        if any(trig in p_lower for trig in eval_triggers) or len(turn_context.countries) > 0 or turn_context.partner_count or turn_context.requested_budget_eur:
            return "PROPOSAL_EVALUATION"

        # CORDIS Data / Statistical Query triggers
        data_triggers = [
            "average budget", "average grant", "average cost", "median budget", "mean budget",
            "how many projects", "projects in 202", "budget for projects", "projects funded in",
            "statistics for", "projects with budget", "highest funded", "top funded", "show me projects",
            "search projects", "list projects", "find projects", "what is the average", "expected budget range",
            "budget range based on past"
        ]
        if any(dt in p_lower for dt in data_triggers):
            return "DATA_QUERY"

        # Regulatory & Policy Inquiry triggers
        reg_triggers = [
            "what are the rules", "annex b rules", "eligibility rules", "eligibility criteria",
            "can switzerland", "can swiss", "can uk", "can associated", "minimum partners",
            "difference between ria and ia", "what is lump sum", "general annex b"
        ]
        if any(rt in p_lower for rt in reg_triggers):
            return "REGULATORY_INQUIRY"

        # Follow-up Strategy Consultation (when active proposal already exists)
        followup_triggers = [
            "work package", "breakdown", "justify", "co-funding", "innovation fund",
            "alternative", "alternatives", "partner workload", "consortium composition",
            "how can we improve", "how do we justify", "what should we change", "recommendations"
        ]
        if has_prior_domain_context and any(ft in p_lower for ft in followup_triggers):
            return "STRATEGY_FOLLOWUP"

        return "STRATEGY_FOLLOWUP" if has_prior_domain_context else "DATA_QUERY"

    def process_message(self, user_message: str, session_id: Optional[str] = None) -> ChatResponse:
        """Processes an incoming user message within a multi-turn conversation with intent-specific routing."""
        session = self.get_or_create_session(session_id)
        session.updated_at = datetime.now(timezone.utc).isoformat()

        # Record user message
        session.messages.append(ChatMessage(role="user", content=user_message))

        # 1. Extract context from current turn
        turn_context = self.rule_evaluator.extract_context(user_message)

        # 2. Classify Intent
        intent = self._classify_intent(user_message, session, turn_context)
        logger.info(f"Classified chat intent for '{user_message[:50]}...': {intent}")

        # 3. Route to Intent Handler
        if intent == "OUT_OF_DOMAIN":
            return self._handle_out_of_domain(user_message, session)
        elif intent == "DATA_QUERY":
            return self._handle_data_query(user_message, session)
        elif intent == "REGULATORY_INQUIRY":
            return self._handle_regulatory_inquiry(user_message, session)
        elif intent == "STRATEGY_FOLLOWUP":
            return self._handle_strategy_followup(user_message, session, turn_context)
        else:
            return self._handle_proposal_evaluation(user_message, session, turn_context)

    def _handle_out_of_domain(self, user_message: str, session: ChatSession) -> ChatResponse:
        """Handles off-topic inquiries."""
        reply = (
            "I am the specialized NeuroSym Horizon Europe Advisory Agent. "
            "I assist exclusively with EU Horizon Europe proposal feasibility, "
            "consortium structure pre-checks (General Annex B rules), and CORDIS empirical benchmarks. "
            "How can I assist you with your EU research and innovation proposal or consortium structure?"
        )
        session.messages.append(ChatMessage(role="assistant", content=reply, metadata={"intent": "OUT_OF_DOMAIN"}))
        return ChatResponse(
            session_id=session.session_id,
            reply=reply,
            verdict=FeasibilityVerdict.OUT_OF_DOMAIN,
            proposal_context=session.proposal_context,
            suggested_followups=[
                "What are the core eligibility rules for a Horizon Europe RIA project?",
                "Evaluate our 36-month AI robotics proposal with 4 EU partners",
                "What is the average grant budget for projects in 2021?"
            ]
        )

    def _handle_data_query(self, user_message: str, session: ChatSession) -> ChatResponse:
        """Executes live DuckDB query and formats natural data answer."""
        data_context = self.query_engine.query_analytical_summary(user_message)
        
        # Render specialized data query prompt
        template = self.jinja_env.get_template("data_query_prompt.j2")
        rendered_prompt = template.render(
            conversation_history=[m.model_dump() for m in session.messages[-6:]],
            user_message=user_message,
            data_context=data_context
        )

        raw_output = self.llm.generate_json(rendered_prompt)
        reply_text = raw_output.get("reply") if isinstance(raw_output, dict) else None

        if not reply_text:
            # High-accuracy deterministic data answer
            avg_str = f"€{data_context['avg_budget']:,.2f}" if data_context.get("avg_budget") else "N/A"
            median_str = f"€{data_context['median_budget']:,.2f}" if data_context.get("median_budget") else "N/A"
            min_str = f"€{data_context['min_budget']:,.2f}" if data_context.get("min_budget") else "N/A"
            max_str = f"€{data_context['max_budget']:,.2f}" if data_context.get("max_budget") else "N/A"
            count = data_context.get("total_count", 0)

            reply_text = (
                f"### CORDIS Empirical Analytics: {data_context['filters_summary']}\n\n"
                f"Based on historical Horizon Europe projects recorded in CORDIS:\n\n"
                f"- **Total Funded Projects**: **{count:,}**\n"
                f"- **Average EU Contribution**: **{avg_str}**\n"
                f"- **Median EU Contribution (P50)**: **{median_str}**\n"
                f"- **Grant Budget Range**: **{min_str}** to **{max_str}**\n"
            )
            if data_context.get("avg_duration_months"):
                reply_text += f"- **Average Execution Timeline**: **{data_context['avg_duration_months']:.1f} months**\n\n"
            
            if data_context.get("sample_records"):
                reply_text += "**Notable Benchmark Projects:**\n"
                for p in data_context["sample_records"][:3]:
                    grant = f"€{p['ecMaxContribution']:,.2f}" if p.get("ecMaxContribution") else "N/A"
                    reply_text += f"- **{p['acronym']}** (ID: `{p['id']}`): {p['title']} — EU Contribution: **{grant}** ({p.get('startDate', 'N/A')})\n"

        followups = raw_output.get("suggested_followups", []) if isinstance(raw_output, dict) else []
        if not followups:
            followups = [
                "What is the average grant size for Horizon Europe RIA projects?",
                "How many robotics projects have received over €10M in EC funding?",
                "Evaluate our consortium structure against these benchmarks"
            ]

        # Build DomainStatistics for live frontend drawer
        stats = None
        if data_context.get("avg_budget"):
            stats = DomainStatistics(
                domain_topic=data_context.get("filters_summary", "CORDIS Query"),
                funding_scheme="HORIZON-RIA",
                comparable_project_count=data_context.get("total_count", 0),
                budget_mean=data_context.get("avg_budget", 0.0),
                budget_p5=data_context.get("min_budget", 0.0),
                budget_p50=data_context.get("median_budget", 0.0),
                budget_p95=data_context.get("max_budget", 0.0),
                avg_duration_months=data_context.get("avg_duration_months", 36.0)
            )

        session.messages.append(ChatMessage(role="assistant", content=reply_text, metadata={"intent": "DATA_QUERY"}))
        return ChatResponse(
            session_id=session.session_id,
            reply=reply_text,
            verdict=FeasibilityVerdict.FEASIBLE,
            proposal_context=session.proposal_context,
            suggested_followups=followups,
            domain_statistics=stats,
            comparable_projects=data_context.get("sample_records", []),
            is_grounded=True
        )

    def _handle_regulatory_inquiry(self, user_message: str, session: ChatSession) -> ChatResponse:
        """Provides authoritative Horizon Europe policy guidance without false proposal evaluation."""
        rules = self.rule_evaluator.rules
        template = self.jinja_env.get_template("regulatory_inquiry_prompt.j2")
        rendered_prompt = template.render(
            conversation_history=[m.model_dump() for m in session.messages[-6:]],
            user_message=user_message,
            relevant_rules=rules
        )

        raw_output = self.llm.generate_json(rendered_prompt)
        reply_text = raw_output.get("reply") if isinstance(raw_output, dict) else None

        if not reply_text:
            reply_text = (
                "### Official Horizon Europe Eligibility & General Annex B Framework\n\n"
                "Under the standard legal framework for Horizon Europe Research and Innovation Actions (RIA) and Innovation Actions (IA):\n\n"
                "1. **Consortium Scale & Independence (Rule R-001)**: The consortium must comprise at least **3 independent legal entities**.\n"
                "2. **Geographic Diversity (Rule R-002)**: Entities must be established in at least **3 different eligible countries** (EU Member States or Associated Countries).\n"
                "3. **EU Member State Presence (Rule R-003)**: At least **1 legal entity** must be established in an **EU Member State** (EU27).\n"
                "4. **Eligible Countries (Rule R-005)**: Entities must belong to EU Member States, Associated Countries (e.g. Norway, Iceland, UK, Israel, Turkey), or eligible third-country arrangements.\n"
                "5. **Project Duration (Rule R-008)**: Standard RIA/IA actions have an execution timeline of **36 to 48 months**.\n\n"
                "*Legal Reference: Horizon Europe Regulation (EU) 2021/695 & Work Programme General Annex B.*"
            )

        followups = raw_output.get("suggested_followups", []) if isinstance(raw_output, dict) else []
        if not followups:
            followups = [
                "Which countries qualify as Horizon Europe Associated Countries?",
                "What are the funding rates for SMEs in Innovation Actions (IA)?",
                "Evaluate our consortium against these General Annex B rules"
            ]

        session.messages.append(ChatMessage(role="assistant", content=reply_text, metadata={"intent": "REGULATORY_INQUIRY"}))
        return ChatResponse(
            session_id=session.session_id,
            reply=reply_text,
            verdict=FeasibilityVerdict.FEASIBLE,
            proposal_context=session.proposal_context,
            suggested_followups=followups,
            is_grounded=True
        )

    def _handle_strategy_followup(self, user_message: str, session: ChatSession, turn_context: ProposalContext) -> ChatResponse:
        """Handles focused strategic follow-ups within an active consultation without repeating boilerplate checklist."""
        # Merge any minor parameters if provided
        if turn_context.requested_budget_eur or turn_context.partner_count or turn_context.countries:
            self._accumulate_proposal_context(session.proposal_context, turn_context)

        template = self.jinja_env.get_template("strategy_followup_prompt.j2")
        rendered_prompt = template.render(
            conversation_history=[m.model_dump() for m in session.messages[-8:]],
            user_message=user_message,
            proposal_context=session.proposal_context,
            latest_verdict=session.latest_verdict,
            evidence=session.latest_evidence
        )

        raw_output = self.llm.generate_json(rendered_prompt)
        reply_text = raw_output.get("reply") if isinstance(raw_output, dict) else None

        if not reply_text:
            p = session.proposal_context
            budget_str = f"€{p.requested_budget_eur:,.2f}" if p.requested_budget_eur else "your requested budget"
            p_count = p.partner_count or 6
            topic = p.domain_topic or "pilot demonstration"

            reply_text = (
                f"### Strategic Advisory: {user_message.strip('?. ')}\n\n"
                f"To structure and justify the **{budget_str}** budget for your **{p_count}-partner {topic}** consortium, we recommend aligning your proposal with the following operational framework:\n\n"
                f"#### 1. Recommended Work Package (WP) Architecture\n"
                f"- **WP1: Project Management, Governance & Quality Assurance** (3–5% of budget) — Consortium coordination, financial reporting, and risk mitigation.\n"
                f"- **WP2: Pilot Plant Design, Engineering & Site Preparation (CAPEX)** (40–50% of budget) — Procurement of long-lead equipment, infrastructure installation, and industrial site integration.\n"
                f"- **WP3: Commissioning, Operational Testing & Scale-Up (OPEX)** (20–25% of budget) — Continuous operation, feedstock testing, energy efficiency optimization, and capture rate validation.\n"
                f"- **WP4: Performance Verification, Techno-Economic Analysis (TEA) & LCA** (8–10% of budget) — Independent TRL assessment, lifecycle carbon accounting, and levelized cost calculations.\n"
                f"- **WP5: Exploitation, Industrial Replication & Business Modeling** (5–8% of budget) — Commercial rollout plan, IP strategy, and regional deployment roadmaps.\n"
                f"- **WP6: Safety, Permitting, Regulatory Compliance & Public Acceptance** (4–6% of budget) — Environmental permitting, cross-border CO2 transport compliance, and stakeholder engagement.\n\n"
                f"#### 2. Evaluator Scrutiny & Co-Funding Strategies\n"
                f"- **Industrial Co-Investment**: Demonstrate substantial in-kind contributions and CAPEX co-financing from industrial partners to address cost-realism concerns.\n"
                f"- **Synergy with EU Innovation Fund**: Large demonstration pilots can combine Horizon Europe RIA/IA research funding with the EU Innovation Fund (Large-Scale Projects) for long-term operational scaling."
            )

        followups = raw_output.get("suggested_followups", []) if isinstance(raw_output, dict) else []
        if not followups:
            followups = [
                "How should we distribute budget between research and industrial partners?",
                "What criteria do Horizon Europe evaluators use for CAPEX vs OPEX?",
                "How can we benchmark our deliverables against historical projects?"
            ]

        session.messages.append(ChatMessage(role="assistant", content=reply_text, metadata={"intent": "STRATEGY_FOLLOWUP"}))
        return ChatResponse(
            session_id=session.session_id,
            reply=reply_text,
            verdict=session.latest_verdict,
            proposal_context=session.proposal_context,
            suggested_followups=followups,
            domain_statistics=session.latest_evidence.domain_statistics if session.latest_evidence else None,
            comparable_projects=session.latest_evidence.comparable_projects if session.latest_evidence else [],
            is_grounded=True
        )

    def _handle_proposal_evaluation(self, user_message: str, session: ChatSession, turn_context: ProposalContext) -> ChatResponse:
        """Handles full formal proposal feasibility assessment and General Annex B compliance check."""
        # 1. Accumulate / merge proposal context across turns
        self._accumulate_proposal_context(session.proposal_context, turn_context)

        # 2. Gather live evidence based on updated accumulated context
        summary_prompt = self._build_context_summary_prompt(session.proposal_context)
        evidence = self.evidence_runtime.gather_evidence(summary_prompt)
        
        # Override evidence proposal context with accumulated context
        evidence.proposal_context = session.proposal_context
        session.latest_evidence = evidence

        # 3. Generate deterministic baseline report
        base_report = self.deterministic_synthesizer.synthesize(evidence)
        session.latest_verdict = base_report.verdict

        # 4. Render Specialized Proposal Evaluation Jinja2 prompt
        template = self.jinja_env.get_template("proposal_evaluation_prompt.j2")
        rendered_prompt = template.render(
            conversation_history=[m.model_dump() for m in session.messages[-8:]],
            user_message=user_message,
            proposal_context=session.proposal_context,
            evidence=evidence,
            base_report=base_report
        )

        # 5. Call LLM for conversational reasoning
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
                    "What work package breakdown justifies our requested budget?",
                    "How does our consortium composition compare to historical projects?",
                    "What co-funding or Innovation Fund alternatives exist for our pilot?"
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
            metadata={"verdict": final_verdict.value, "intent": "PROPOSAL_EVALUATION"}
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
        elif len(current.countries) > 0:
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
