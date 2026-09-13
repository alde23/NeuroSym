"""Horizon Europe Rule Engine & Decision Evaluator connecting Duckling, DuckDB benchmarks, and rule sets."""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import duckdb

from neurosym.duckling.client import DucklingClient
from neurosym.ingestion.cordis_ingest import COUNTRY_MAP, DEFAULT_DB_PATH
from neurosym.intent.mapper import TOPIC_ALIASES
from neurosym.rules.models import (
    DomainStatistics,
    EvaluationReport,
    FeasibilityVerdict,
    ProposalContext,
    Rule,
    RuleEvaluation,
    RuleSource,
    RuleStatus,
    Severity,
)

logger = logging.getLogger(__name__)

RULES_FILE = Path(__file__).parent / "eu_horizon_rules.json"


class RuleEvaluator:
    """Evaluates Horizon Europe proposals against official rules, CORDIS percentiles, and company policies."""

    def __init__(self, rules_path: Path = RULES_FILE, db_path: Path = DEFAULT_DB_PATH):
        self.rules_path = Path(rules_path)
        self.db_path = Path(db_path)
        self.duckling = DucklingClient()
        self._load_rules()

    def _load_rules(self):
        with open(self.rules_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.domain_id = data.get("domain_id")
        self.name = data.get("name")
        self.description = data.get("description")
        self.named_sets = data.get("named_sets", {})
        self.rules = [Rule.model_validate(r) for r in data.get("rules", [])]

    def get_rules_catalog(self) -> List[Rule]:
        """Returns all registered rules in the domain."""
        return self.rules

    def extract_context(self, prompt: str) -> ProposalContext:
        """Extracts structured proposal context from prompt using Duckling and domain vocabularies."""
        duckling_entities = self.duckling.extract_entities(prompt)
        prompt_lower = prompt.lower()

        context = ProposalContext(raw_prompt=prompt)

        # 1. Duckling dimensions
        for ent in duckling_entities:
            if ent.dim == "number":
                before = prompt_lower[:ent.start]
                after = prompt_lower[ent.end:]
                # Partner count check
                if any(w in after[:30] for w in ["institution", "partner", "organisation", "organization", "entit", "member"]):
                    context.partner_count = int(ent.num_value)
                elif any(w in before[-25:] for w in ["consortium of", "consortium with", "team of"]):
                    context.partner_count = int(ent.num_value)
                # Duration check if stated as "36 months"
                elif any(w in after[:20] for w in ["month", "months", "mo"]):
                    context.requested_duration_months = int(ent.num_value)
                elif any(w in after[:20] for w in ["year", "years", "yr"]):
                    context.requested_duration_months = int(ent.num_value * 12)

            elif ent.dim == "duration":
                if ent.duration_unit == "year":
                    context.requested_duration_months = int(ent.duration_val * 12)
                elif ent.duration_unit == "month":
                    context.requested_duration_months = int(ent.duration_val)

            elif ent.dim == "amount-of-money":
                if ent.min_amount is not None:
                    context.requested_budget_eur = ent.min_amount
                elif ent.num_value is not None:
                    context.requested_budget_eur = ent.num_value

        # Regex fallback for duration if written as "36-month"
        if context.requested_duration_months is None:
            m = re.search(r"\b(\d+)[-\s]month", prompt_lower)
            if m:
                context.requested_duration_months = int(m.group(1))
            else:
                m_yr = re.search(r"\b(\d+)[-\s]year", prompt_lower)
                if m_yr:
                    context.requested_duration_months = int(m_yr.group(1)) * 12

        # 2. Extract countries
        eu27 = set(self.named_sets.get("EU27", []))
        associated = set(self.named_sets.get("ASSOCIATED", []))
        found_countries = set()

        for code, name in COUNTRY_MAP.items():
            pattern = rf"\b{name.lower()}\b"
            if re.search(pattern, prompt_lower):
                found_countries.add(code)
            elif re.search(rf"\b{code}\b", prompt):
                found_countries.add(code)

        context.countries = sorted(list(found_countries))
        context.distinct_country_count = len(context.countries)
        context.member_state_count = sum(1 for c in context.countries if c in eu27)
        context.associated_country_count = sum(1 for c in context.countries if c in associated)
        context.third_country_count = sum(1 for c in context.countries if c not in eu27 and c not in associated)

        # 3. Funding scheme
        schemes = {
            "research and innovation action": "HORIZON-RIA",
            "ria": "HORIZON-RIA",
            "innovation action": "HORIZON-IA",
            "ia": "HORIZON-IA",
            "coordination and support": "HORIZON-CSA",
            "csa": "HORIZON-CSA",
            "erc": "HORIZON-ERC",
            "msca": "HORIZON-MSCA"
        }
        for kw, code in schemes.items():
            if re.search(rf"\b{kw}\b", prompt_lower):
                context.funding_scheme = code
                break

        # If funding scheme not explicitly stated but consortium structure or duration is present, default to HORIZON-RIA
        if context.funding_scheme is None and (context.partner_count is not None or len(context.countries) > 0 or context.requested_duration_months is not None):
            context.funding_scheme = "HORIZON-RIA"

        # 4. Role
        if "coordinate" in prompt_lower or "coordinator" in prompt_lower or "lead" in prompt_lower:
            context.our_role = "coordinator"
        elif "partner" in prompt_lower or "participant" in prompt_lower:
            context.our_role = "partner"

        # 5. Topic / domain
        for canonical, aliases in TOPIC_ALIASES.items():
            for alias in aliases:
                if re.search(rf"\b{alias}\b", prompt_lower):
                    context.domain_topic = canonical
                    break
            if context.domain_topic:
                break

        # 6. Domain relevance check
        domain_keywords = [
            "horizon", "horizon europe", "cordis", "fp7", "fp8", "fp9", "h2020",
            "consortium", "consortiums", "ria", "ia", "csa", "erc", "msca", "eic",
            "research and innovation", "innovation action", "grant", "grants",
            "proposal", "proposals", "work programme", "call for proposals",
            "european commission", "eu project", "eu funding", "framework programme",
            "annex b", "deliverable", "deliverables", "work package", "work packages",
            "coordinator", "coordinating", "eligibility", "feasibility",
            "project", "projects", "institution", "institutions", "university", "universities", "sme", "smes"
        ]
        has_domain_kw = any(re.search(rf"\b{re.escape(kw)}\b", prompt_lower) for kw in domain_keywords)
        has_scheme = context.funding_scheme is not None
        has_topic = context.domain_topic is not None
        has_consortium_structure = (
            (context.partner_count is not None and (len(context.countries) > 0 or context.requested_duration_months is not None)) or
            (len(context.countries) >= 2)
        )

        if has_domain_kw or has_consortium_structure or (has_topic and len(context.countries) > 0):
            context.is_domain_relevant = True
        else:
            context.is_domain_relevant = False
            context.out_of_domain_reason = (
                "The prompt does not pertain to EU Horizon Europe, research grants, consortium feasibility, or CORDIS data."
            )

        return context

    def compute_statistics(self, context: ProposalContext) -> Optional[DomainStatistics]:
        """Queries live DuckDB database for empirical percentiles and benchmarks for comparable projects."""
        if not self.db_path.exists():
            return None

        scheme = context.funding_scheme or "HORIZON-RIA"
        topic = context.domain_topic

        where_clauses = ["fundingScheme LIKE ?"]
        params = [f"%{scheme}%"]

        if topic:
            where_clauses.append("(scientific_topics ILIKE ? OR title ILIKE ? OR objective ILIKE ?)")
            params.extend([f"%{topic}%", f"%{topic}%", f"%{topic}%"])

        where_sql = " AND ".join(where_clauses)

        with duckdb.connect(str(self.db_path), read_only=True) as con:
            query = f"""
            SELECT
                COUNT(*) AS total,
                COALESCE(QUANTILE_CONT(totalCost, 0.05), 0.0) AS p5,
                COALESCE(QUANTILE_CONT(totalCost, 0.25), 0.0) AS p25,
                COALESCE(QUANTILE_CONT(totalCost, 0.50), 0.0) AS p50,
                COALESCE(QUANTILE_CONT(totalCost, 0.75), 0.0) AS p75,
                COALESCE(QUANTILE_CONT(totalCost, 0.95), 0.0) AS p95,
                COALESCE(QUANTILE_CONT(totalCost, 0.98), 0.0) AS p98,
                COALESCE(AVG(totalCost), 0.0) AS mean_cost,
                COALESCE(AVG(num_organizations), 0.0) AS avg_partners,
                COALESCE(MEDIAN(num_organizations), 0.0) AS median_partners,
                COALESCE(AVG(DATEDIFF('month', startDate, endDate)), 36.0) AS avg_duration
            FROM v_project_enriched
            WHERE {where_sql} AND totalCost > 0
            """
            row = con.execute(query, params).fetchone()
            if not row or row[0] == 0:
                # Fallback to scheme only if topic is too narrow
                query_fallback = f"""
                SELECT
                    COUNT(*),
                    COALESCE(QUANTILE_CONT(totalCost, 0.05), 0.0),
                    COALESCE(QUANTILE_CONT(totalCost, 0.25), 0.0),
                    COALESCE(QUANTILE_CONT(totalCost, 0.50), 0.0),
                    COALESCE(QUANTILE_CONT(totalCost, 0.75), 0.0),
                    COALESCE(QUANTILE_CONT(totalCost, 0.95), 0.0),
                    COALESCE(QUANTILE_CONT(totalCost, 0.98), 0.0),
                    COALESCE(AVG(totalCost), 0.0),
                    COALESCE(AVG(num_organizations), 0.0),
                    COALESCE(MEDIAN(num_organizations), 0.0),
                    COALESCE(AVG(DATEDIFF('month', startDate, endDate)), 36.0)
                FROM v_project_enriched
                WHERE fundingScheme LIKE ? AND totalCost > 0
                """
                row = con.execute(query_fallback, [f"%{scheme}%"]).fetchone()

            stats = DomainStatistics(
                comparable_project_count=row[0],
                funding_scheme=scheme,
                topic=topic,
                budget_p5=round(row[1], 2),
                budget_p25=round(row[2], 2),
                budget_p50=round(row[3], 2),
                budget_p75=round(row[4], 2),
                budget_p95=round(row[5], 2),
                budget_p98=round(row[6], 2),
                budget_mean=round(row[7], 2),
                avg_partner_count=round(row[8], 1),
                median_partner_count=round(row[9], 1),
                avg_duration_months=round(row[10], 1),
            )

            # Compute requested budget percentile rank
            if context.requested_budget_eur is not None and row[0] > 0:
                rank_sql = f"""
                SELECT 100.0 * COUNT(CASE WHEN totalCost <= ? THEN 1 END) / COUNT(*)
                FROM v_project_enriched
                WHERE {where_sql} AND totalCost > 0
                """
                rank_res = con.execute(rank_sql, [context.requested_budget_eur] + params).fetchone()
                if rank_res:
                    stats.requested_budget_percentile = round(rank_res[0], 1)

            return stats

    def evaluate(self, prompt: str) -> EvaluationReport:
        """Runs full evaluation pipeline: extraction -> live benchmarks -> rule check -> verdict."""
        context = self.extract_context(prompt)
        
        if not context.is_domain_relevant:
            return EvaluationReport(
                verdict=FeasibilityVerdict.OUT_OF_DOMAIN,
                summary="Out of Domain: The request does not relate to EU Horizon Europe proposals, CORDIS historical data, or research consortium eligibility.",
                proposal=context,
                statistics=None,
                evaluations=[],
                errors=[],
                warnings=[]
            )

        stats = self.compute_statistics(context)

        evaluations: List[RuleEvaluation] = []
        errors: List[str] = []
        warnings: List[str] = []

        consortium_schemes = set(self.named_sets.get("CONSORTIUM_SCHEMES", []))

        for rule in self.rules:
            # 1. Check applies_when
            if rule.applies_when:
                app_field = getattr(context, rule.applies_when.field, None)
                if rule.applies_when.op == "in":
                    named_set = self.named_sets.get(rule.applies_when.value, [])
                    if app_field not in named_set:
                        continue
                elif rule.applies_when.op == "==":
                    if app_field != rule.applies_when.value:
                        continue

            actual_val = getattr(context, rule.field, None)
            status = RuleStatus.PASSED
            evidence_details = {}

            # 2. Evaluate operator
            if rule.op == ">=":
                if actual_val is None or actual_val < rule.value:
                    status = RuleStatus.FAILED
            elif rule.op == "<=":
                if actual_val is not None and actual_val > rule.value:
                    status = RuleStatus.FAILED
            elif rule.op == "==":
                if actual_val is not None and actual_val != rule.value:
                    status = RuleStatus.FAILED
            elif rule.op == "within_percentile":
                # Benchmark percentile rule
                if stats and context.requested_budget_eur is not None:
                    p_low, p_high = rule.value
                    is_within = (stats.budget_p5 <= context.requested_budget_eur <= stats.budget_p95)
                    evidence_details = {
                        "requested_budget": context.requested_budget_eur,
                        "p5": stats.budget_p5,
                        "p50": stats.budget_p50,
                        "p95": stats.budget_p95,
                        "percentile_rank": stats.requested_budget_percentile,
                        "comparable_projects": stats.comparable_project_count
                    }
                    if not is_within:
                        status = RuleStatus.FAILED
                        # Custom message formatting
                        if context.requested_budget_eur > stats.budget_p95:
                            msg = f"Requested budget of €{context.requested_budget_eur:,.2f} is in the {stats.requested_budget_percentile}th percentile (exceeds 95th percentile benchmark of €{stats.budget_p95:,.2f} among comparable {stats.topic or stats.funding_scheme} projects)."
                        else:
                            msg = f"Requested budget of €{context.requested_budget_eur:,.2f} is in the {stats.requested_budget_percentile}th percentile (below 5th percentile benchmark of €{stats.budget_p5:,.2f})."
                        rule_eval_msg = msg
                else:
                    status = RuleStatus.SKIPPED

            rule_eval_msg = rule.message if status == RuleStatus.FAILED else f"Rule satisfied: {rule.name}"

            eval_entry = RuleEvaluation(
                rule_id=rule.rule_id,
                name=rule.name,
                source=rule.source,
                severity=rule.severity,
                status=status,
                field=rule.field,
                actual_value=actual_val,
                required_condition=f"{rule.field} {rule.op} {rule.value}",
                message=rule.message if status == RuleStatus.FAILED else "Condition satisfied",
                reference=rule.reference,
                evidence_details=evidence_details if evidence_details else None
            )
            evaluations.append(eval_entry)

            if status == RuleStatus.FAILED:
                if rule.severity == Severity.ERROR:
                    errors.append(f"[{rule.rule_id}] {rule.message}")
                elif rule.severity == Severity.WARNING:
                    warnings.append(f"[{rule.rule_id}] {rule_eval_msg}")

        # Determine overall verdict
        if errors:
            verdict = FeasibilityVerdict.INFEASIBLE
            summary = f"Proposal INFEASIBLE due to {len(errors)} critical eligibility / policy violation(s)."
        elif warnings:
            verdict = FeasibilityVerdict.CONDITIONALLY_FEASIBLE
            summary = f"Proposal CONDITIONALLY FEASIBLE with {len(warnings)} caution / benchmark warning(s)."
        else:
            verdict = FeasibilityVerdict.FEASIBLE
            summary = "Proposal FEASIBLE: SATISFIES all core Horizon Europe eligibility and policy requirements."

        return EvaluationReport(
            verdict=verdict,
            summary=summary,
            proposal=context,
            statistics=stats,
            evaluations=evaluations,
            errors=errors,
            warnings=warnings
        )
