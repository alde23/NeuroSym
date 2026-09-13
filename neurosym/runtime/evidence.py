"""Evidence Runtime for gathering deterministic factual evidence from Duckling, DuckDB, and Rules."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from neurosym.duckling.client import DucklingClient
from neurosym.ingestion.cordis_ingest import DEFAULT_DB_PATH
from neurosym.intent.intent_schema import IntentSchema
from neurosym.intent.mapper import IntentMapper
from neurosym.query.engine import QueryEngine, QueryResult
from neurosym.rules.evaluator import RuleEvaluator
from neurosym.rules.models import DomainStatistics, ProposalContext, RuleEvaluation

logger = logging.getLogger(__name__)


class EvidencePacket(BaseModel):
    """
    Immutable structured collection of all deterministic evidence gathered from
    Duckling entity extraction, Master Schema queries, live DuckDB statistics,
    and rule evaluation results.
    """
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw_prompt: str
    
    # 1. Extracted Entities & Intent
    extracted_entities: List[Dict[str, Any]] = Field(default_factory=list)
    intent_schema: IntentSchema
    
    # 2. Proposal Context
    proposal_context: ProposalContext
    
    # 3. Rule Compliance Evidence
    rule_evaluations: List[RuleEvaluation] = Field(default_factory=list)
    has_critical_errors: bool = False
    has_warnings: bool = False
    
    # 4. Empirical Statistical Evidence (from live DuckDB)
    domain_statistics: Optional[DomainStatistics] = None
    
    # 5. Comparable Historical Projects (Grounded references)
    comparable_projects: List[Dict[str, Any]] = Field(default_factory=list)
    
    # 6. Raw SQL Queries Executed
    executed_queries: List[str] = Field(default_factory=list)


class EvidenceRuntime:
    """
    Executes the deterministic data retrieval pipeline based on user prompt,
    intent schema, rule set, and DuckDB analytical queries.
    """

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.duckling = DucklingClient()
        self.intent_mapper = IntentMapper(duckling_client=self.duckling)
        self.query_engine = QueryEngine(self.db_path)
        self.rule_evaluator = RuleEvaluator(db_path=self.db_path)

    def gather_evidence(self, prompt: str) -> EvidencePacket:
        """
        Executes all deterministic extraction and querying steps to produce
        an immutable EvidencePacket.
        """
        logger.info(f"Gathering evidence for prompt: '{prompt[:50]}...'")

        # 1. Intent Mapping
        intent = self.intent_mapper.parse_and_map(prompt)

        # 2. Proposal Context & Rule Evaluation
        report = self.rule_evaluator.evaluate(prompt)
        proposal_ctx = report.proposal
        rule_evals = report.evaluations
        stats = report.statistics

        # 3. Query Comparable Historical Projects from DuckDB
        query_res = self.query_engine.execute(intent)
        comparable_projs = query_res.records[:5]

        has_errors = len(report.errors) > 0
        has_warnings = len(report.warnings) > 0

        packet = EvidencePacket(
            raw_prompt=prompt,
            extracted_entities=intent.extracted_duckling_entities,
            intent_schema=intent,
            proposal_context=proposal_ctx,
            rule_evaluations=rule_evals,
            has_critical_errors=has_errors,
            has_warnings=has_warnings,
            domain_statistics=stats,
            comparable_projects=comparable_projs,
            executed_queries=[query_res.generated_sql]
        )

        return packet
