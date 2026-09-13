"""Query Execution Engine translating Intent Schema into DuckDB SQL and fetching referenced data."""

import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import duckdb
from pydantic import BaseModel, Field

from neurosym.ingestion.cordis_ingest import DEFAULT_DB_PATH, ensure_database_ready
from neurosym.intent.intent_schema import IntentSchema, Operator, SortOrder

logger = logging.getLogger(__name__)


class QueryResult(BaseModel):
    """Structured response containing executed query, stats, and referenced dataset records."""
    prompt: str
    target_entity: str
    generated_sql: str
    execution_time_ms: float
    total_matches: int
    records: List[Dict[str, Any]] = Field(default_factory=list)


class QueryEngine:
    """Compiles IntentSchema into DuckDB SQL and executes against the CORDIS database."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        ensure_database_ready(self.db_path)

    def execute(self, intent: IntentSchema) -> QueryResult:
        """Translates intent to SQL, executes against DuckDB, and returns referenced records."""
        sql, params = self.compile_sql(intent)
        
        t0 = time.time()
        with duckdb.connect(str(self.db_path), read_only=True) as con:
            cursor = con.execute(sql, params)
            columns = [desc[0] for desc in cursor.description]
            raw_rows = cursor.fetchall()
            
            records = []
            for row in raw_rows:
                record = dict(zip(columns, row))
                
                # If target is project, fetch connected organizations and topics
                if intent.target_entity == "project" and "id" in record:
                    proj_id = record["id"]
                    orgs = con.execute("""
                        SELECT name, shortName, country, role, SME, ecContribution 
                        FROM organization 
                        WHERE projectID = ? 
                        ORDER BY role = 'coordinator' DESC, ecContribution DESC NULLS LAST
                        LIMIT 5
                    """, [proj_id]).fetchall()
                    record["top_organizations"] = [
                        {
                            "name": o[0], "shortName": o[1], "country": o[2],
                            "role": o[3], "SME": o[4], "ecContribution": o[5]
                        } for o in orgs
                    ]

                    topics = con.execute("""
                        SELECT euroSciVocTitle 
                        FROM euroSciVoc 
                        WHERE projectID = ? 
                        LIMIT 5
                    """, [proj_id]).fetchall()
                    record["euroSciVoc_topics"] = [t[0] for t in topics]

                records.append(record)

        elapsed_ms = (time.time() - t0) * 1000

        return QueryResult(
            prompt=intent.prompt,
            target_entity=intent.target_entity,
            generated_sql=sql,
            execution_time_ms=round(elapsed_ms, 2),
            total_matches=len(records),
            records=records
        )

    def compile_sql(self, intent: IntentSchema) -> Tuple[str, List[Any]]:
        """Generates parameterized SQL string and parameter values."""
        target = intent.target_entity
        
        # Select columns
        proj_cols = [f"{target}.{p}" for p in intent.projections] if intent.projections else [f"{target}.*"]
        select_clause = "SELECT DISTINCT " + ", ".join(proj_cols)

        from_clause = f"FROM {target}"
        joins = []
        joined_tables = {target}

        # Check required joins from filter entities
        for f in intent.filters:
            ent = f.entity
            if ent not in joined_tables:
                if target == "project":
                    if ent in ("organization", "euroSciVoc", "topics", "legalBasis", "projectDeliverables", "projectPublications", "policyPriorities"):
                        joins.append(f"LEFT JOIN {ent} ON project.id = {ent}.projectID")
                        joined_tables.add(ent)
                elif target == "organization":
                    if ent == "project":
                        joins.append("LEFT JOIN project ON organization.projectID = project.id")
                        joined_tables.add("project")
                    elif ent in ("euroSciVoc", "topics", "legalBasis", "projectDeliverables", "projectPublications", "policyPriorities"):
                        joins.append(f"LEFT JOIN {ent} ON organization.projectID = {ent}.projectID")
                        joined_tables.add(ent)
                elif target in ("projectDeliverables", "projectPublications", "euroSciVoc"):
                    if ent == "project":
                        joins.append(f"LEFT JOIN project ON {target}.projectID = project.id")
                        joined_tables.add("project")
                    elif ent == "organization":
                        joins.append(f"LEFT JOIN organization ON {target}.projectID = organization.projectID")
                        joined_tables.add("organization")

        where_clauses = []
        params = []

        for f in intent.filters:
            col_ref = f"{f.entity}.{f.parameter}"
            if f.operator == Operator.EQ:
                where_clauses.append(f"{col_ref} = ?")
                params.append(f.value)
            elif f.operator == Operator.NEQ:
                where_clauses.append(f"{col_ref} != ?")
                params.append(f.value)
            elif f.operator == Operator.GT:
                where_clauses.append(f"{col_ref} > ?")
                params.append(f.value)
            elif f.operator == Operator.GTE:
                where_clauses.append(f"{col_ref} >= ?")
                params.append(f.value)
            elif f.operator == Operator.LT:
                where_clauses.append(f"{col_ref} < ?")
                params.append(f.value)
            elif f.operator == Operator.LTE:
                where_clauses.append(f"{col_ref} <= ?")
                params.append(f.value)
            elif f.operator == Operator.BETWEEN:
                where_clauses.append(f"{col_ref} BETWEEN ? AND ?")
                params.append(f.value)
                params.append(f.value_to)
            elif f.operator in (Operator.LIKE, Operator.CONTAINS):
                where_clauses.append(f"LOWER({col_ref}) LIKE LOWER(?)")
                params.append(f.value)
            elif f.operator == Operator.IS_TRUE:
                where_clauses.append(f"{col_ref} = TRUE")
            elif f.operator == Operator.IS_FALSE:
                where_clauses.append(f"{col_ref} = FALSE")

        sql_parts = [select_clause, from_clause]
        if joins:
            sql_parts.extend(joins)
        if where_clauses:
            sql_parts.append("WHERE " + " AND ".join(where_clauses))

        # Order by
        if intent.order_by:
            order_strs = [f"{ob.entity}.{ob.parameter} {ob.order.value} NULLS LAST" for ob in intent.order_by]
            sql_parts.append("ORDER BY " + ", ".join(order_strs))

        # Limit & Offset
        sql_parts.append(f"LIMIT {intent.limit}")
        if intent.offset > 0:
            sql_parts.append(f"OFFSET {intent.offset}")

        full_sql = "\n".join(sql_parts)
        return full_sql, params

    def query_analytical_summary(self, prompt: str) -> Dict[str, Any]:
        """
        Extracts temporal/thematic filters from natural language data questions and
        executes live statistical aggregations in DuckDB.
        """
        p_lower = prompt.lower()
        where_clauses = ["project.ecMaxContribution IS NOT NULL"]
        params: List[Any] = []
        applied_filters: List[str] = []

        # 1. Year detection
        year_match = re.search(r"\b(202[1-7])\b", prompt)
        if year_match:
            y = int(year_match.group(1))
            where_clauses.append("YEAR(project.startDate) = ?")
            params.append(y)
            applied_filters.append(f"Start Year: {y}")

        # 2. Topic / keyword detection
        from neurosym.intent.mapper import TOPIC_ALIASES
        matched_topic = None
        for canonical, aliases in TOPIC_ALIASES.items():
            if any(alias in p_lower for alias in aliases):
                matched_topic = canonical
                break
        
        join_euroscivoc = False
        if matched_topic:
            join_euroscivoc = True
            where_clauses.append("(LOWER(project.title) LIKE ? OR LOWER(euroSciVoc.euroSciVocTitle) LIKE ? OR LOWER(project.topics) LIKE ?)")
            term = f"%{matched_topic}%"
            params.extend([term, term, term])
            applied_filters.append(f"Topic: {matched_topic}")

        # 3. Funding scheme detection
        if "ria" in p_lower or "research and innovation action" in p_lower:
            where_clauses.append("project.fundingScheme LIKE '%RIA%'")
            applied_filters.append("Scheme: HORIZON-RIA")
        elif "ia" in p_lower or "innovation action" in p_lower:
            where_clauses.append("project.fundingScheme LIKE '%IA%'")
            applied_filters.append("Scheme: HORIZON-IA")
        elif "csa" in p_lower:
            where_clauses.append("project.fundingScheme LIKE '%CSA%'")
            applied_filters.append("Scheme: HORIZON-CSA")

        from_sql = "FROM project"
        if join_euroscivoc:
            from_sql += " LEFT JOIN euroSciVoc ON project.id = euroSciVoc.projectID"

        where_sql = "WHERE " + " AND ".join(where_clauses)

        stats_sql = f"""
            SELECT 
                COUNT(DISTINCT project.id) AS total_count,
                AVG(project.ecMaxContribution) AS avg_budget,
                MEDIAN(project.ecMaxContribution) AS median_budget,
                MIN(project.ecMaxContribution) AS min_budget,
                MAX(project.ecMaxContribution) AS max_budget,
                AVG(CASE WHEN project.endDate IS NOT NULL AND project.startDate IS NOT NULL 
                    THEN (date_diff('month', project.startDate, project.endDate)) END) AS avg_duration_months
            {from_sql}
            {where_sql}
        """

        samples_sql = f"""
            SELECT DISTINCT project.id, project.acronym, project.title, project.ecMaxContribution, project.startDate, project.fundingScheme, project.frameworkProgramme
            {from_sql}
            {where_sql}
            ORDER BY project.ecMaxContribution DESC NULLS LAST
            LIMIT 5
        """

        with duckdb.connect(str(self.db_path), read_only=True) as con:
            stats_row = con.execute(stats_sql, params).fetchone()
            samples_rows = con.execute(samples_sql, params).fetchall()

        total_count = stats_row[0] if stats_row else 0
        avg_budget = stats_row[1] if stats_row and stats_row[1] is not None else None
        median_budget = stats_row[2] if stats_row and stats_row[2] is not None else None
        min_budget = stats_row[3] if stats_row and stats_row[3] is not None else None
        max_budget = stats_row[4] if stats_row and stats_row[4] is not None else None
        avg_duration = stats_row[5] if stats_row and stats_row[5] is not None else None

        sample_records = [
            {
                "id": r[0], "acronym": r[1], "title": r[2],
                "ecMaxContribution": r[3], "startDate": str(r[4]) if r[4] else None,
                "fundingScheme": r[5], "frameworkProgramme": r[6]
            }
            for r in samples_rows
        ]

        return {
            "target_entity": "project",
            "filters_summary": ", ".join(applied_filters) if applied_filters else "All Horizon Europe Projects",
            "total_count": total_count,
            "avg_budget": avg_budget,
            "median_budget": median_budget,
            "min_budget": min_budget,
            "max_budget": max_budget,
            "avg_duration_months": avg_duration,
            "sample_records": sample_records
        }
