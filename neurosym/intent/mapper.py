"""Intent Schema Mapper connecting Duckling extracted entities and domain vocabularies to Master Schema."""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from neurosym.duckling.client import DucklingClient, ExtractedEntity
from neurosym.ingestion.cordis_ingest import COUNTRY_MAP, DEFAULT_SCHEMA_PATH
from neurosym.intent.intent_schema import (
    Aggregation,
    FilterClause,
    IntentSchema,
    Operator,
    OrderByClause,
    SortOrder,
)
from neurosym.schema.master_schema import DucklingDimension, MasterSchema

logger = logging.getLogger(__name__)

# Topic and keyword alias dictionary
TOPIC_ALIASES = {
    "artificial intelligence": ["ai", "artificial intelligence", "deep learning", "neural networks"],
    "machine learning": ["machine learning", "ml"],
    "robotics": ["robotics", "robots", "autonomous systems"],
    "quantum": ["quantum", "quantum computing", "quantum physics"],
    "photovoltaics": ["photovoltaics", "solar", "solar cells", "pv"],
    "hydrogen": ["hydrogen", "fuel cells", "clean hydrogen"],
    "batteries": ["batteries", "energy storage", "battery"],
    "renewable energy": ["renewable energy", "renewables", "clean energy"],
    "oncology": ["oncology", "cancer", "tumour", "tumor"],
    "neuroscience": ["neuroscience", "brain", "neurology"],
    "climate change": ["climate change", "global warming", "climate adaptation"],
    "biodiversity": ["biodiversity", "ecosystems", "wildlife"],
    "cybersecurity": ["cybersecurity", "cyber security", "network security"],
    "genomics": ["genomics", "genetics", "dna sequencing"],
    "nanotechnology": ["nanotechnology", "nanomaterials", "nanoscale"],
    "biomass": ["biomass", "biofuels", "bioenergy"],
    "agriculture": ["agriculture", "farming", "agritech"],
    "carbon capture": ["ccus", "carbon capture", "carbon capture and storage", "ccs", "co2 capture", "carbon removal", "direct air capture"],
    "circular economy": ["circular economy", "recycling", "waste reduction"],
    "decarbonization": ["decarbonization", "net-zero", "emission reduction", "clean tech"],
    "graphene": ["graphene", "2d materials"],
    "vaccines": ["vaccines", "immunology", "vaccination"]
}


class IntentMapper:
    """
    Transforms natural language prompts into a formal IntentSchema by combining
    Duckling entity extraction with Master Schema parameter mapping.
    """

    def __init__(self, master_schema: Optional[MasterSchema] = None, duckling_client: Optional[DucklingClient] = None):
        if master_schema is None:
            if DEFAULT_SCHEMA_PATH.exists():
                with open(DEFAULT_SCHEMA_PATH, "r", encoding="utf-8") as f:
                    self.master_schema = MasterSchema.model_validate_json(f.read())
            else:
                self.master_schema = MasterSchema()
        else:
            self.master_schema = master_schema

        self.duckling = duckling_client or DucklingClient()

    def parse_and_map(self, prompt: str) -> IntentSchema:
        """Full pipeline: extracts Duckling entities, detects domain concepts, and maps to IntentSchema."""
        # 1. Extract Duckling entities
        duckling_entities = self.duckling.extract_entities(prompt)

        # 2. Determine Target Entity
        target_entity = self._detect_target_entity(prompt)

        # 3. Initialize Intent Schema
        intent = IntentSchema(
            target_entity=target_entity,
            prompt=prompt,
            extracted_duckling_entities=[e.model_dump() for e in duckling_entities],
        )

        # 4. Map Duckling Entities to Filters
        self._map_duckling_entities(prompt, duckling_entities, intent)

        # 5. Extract Domain Concepts (Countries, Topics, SMEs, Roles, Funding)
        matched_domain = self._map_domain_concepts(prompt, intent)
        intent.matched_domain_entities = matched_domain

        # 6. Apply Default Sorting and Limit
        self._apply_projections_and_ordering(intent)

        return intent

    def _detect_target_entity(self, prompt: str) -> str:
        prompt_lower = prompt.lower()
        if any(w in prompt_lower for w in ["organizations", "organisations", "universities", "institutes", "companies", "partners", "coordinators"]):
            if not any(w in prompt_lower for w in ["projects with", "projects having", "projects funded"]):
                return "organization"
        if any(w in prompt_lower for w in ["publications", "papers", "articles", "journals"]):
            return "projectPublications"
        if any(w in prompt_lower for w in ["deliverables", "prototypes"]):
            return "projectDeliverables"
        return "project"

    def _map_duckling_entities(self, prompt: str, entities: List[ExtractedEntity], intent: IntentSchema):
        prompt_lower = prompt.lower()

        for ent in entities:
            if ent.dim == "amount-of-money":
                param = "totalCost"
                if "contribution" in prompt_lower or "grant" in prompt_lower or "award" in prompt_lower:
                    param = "ecMaxContribution"
                elif intent.target_entity == "organization":
                    param = "ecContribution"

                target_tbl = "organization" if intent.target_entity == "organization" else "project"

                if ent.val_type == "interval":
                    if ent.min_amount is not None:
                        intent.filters.append(FilterClause(
                            entity=target_tbl,
                            parameter=param,
                            operator=Operator.GTE,
                            value=ent.min_amount,
                            source_entity="duckling:amount-of-money",
                            description=f"{param} >= €{ent.min_amount:,.2f}"
                        ))
                    if ent.max_amount is not None:
                        intent.filters.append(FilterClause(
                            entity=target_tbl,
                            parameter=param,
                            operator=Operator.LTE,
                            value=ent.max_amount,
                            source_entity="duckling:amount-of-money",
                            description=f"{param} <= €{ent.max_amount:,.2f}"
                        ))
                elif ent.num_value is not None:
                    before_text = prompt_lower[:ent.start]
                    if any(w in before_text[-25:] for w in ["more than", "over", "above", "exceeding", "at least", "min", ">="]):
                        op = Operator.GTE
                    elif any(w in before_text[-25:] for w in ["less than", "under", "below", "max", "up to", "<="]):
                        op = Operator.LTE
                    else:
                        op = Operator.GTE

                    intent.filters.append(FilterClause(
                        entity=target_tbl,
                        parameter=param,
                        operator=op,
                        value=ent.num_value,
                        source_entity="duckling:amount-of-money",
                        description=f"{param} {op.value} €{ent.num_value:,.2f}"
                    ))

            elif ent.dim == "time":
                before_text = prompt_lower[:ent.start]
                is_end_date = any(w in before_text[-25:] for w in ["end", "finish", "complete", "before", "until", "by", "ending"])
                param = "endDate" if is_end_date else "startDate"

                if ent.val_type == "interval":
                    if ent.start_date:
                        intent.filters.append(FilterClause(
                            entity="project",
                            parameter="startDate",
                            operator=Operator.GTE,
                            value=ent.start_date,
                            source_entity="duckling:time",
                            description=f"startDate >= {ent.start_date}"
                        ))
                    if ent.end_date:
                        intent.filters.append(FilterClause(
                            entity="project",
                            parameter="endDate",
                            operator=Operator.LTE,
                            value=ent.end_date,
                            source_entity="duckling:time",
                            description=f"endDate <= {ent.end_date}"
                        ))
                elif ent.start_date:
                    if any(w in before_text[-25:] for w in ["after", "from", "since", "starting", "start", "starting after"]):
                        op = Operator.GTE
                        val = ent.start_date
                    elif any(w in before_text[-25:] for w in ["before", "until", "by", "ending before"]):
                        op = Operator.LTE
                        val = ent.start_date
                    elif ent.grain == "year":
                        year = ent.start_date[:4]
                        intent.filters.append(FilterClause(
                            entity="project",
                            parameter=param,
                            operator=Operator.BETWEEN,
                            value=f"{year}-01-01",
                            value_to=f"{year}-12-31",
                            source_entity="duckling:time",
                            description=f"{param} in year {year}"
                        ))
                        continue
                    else:
                        op = Operator.GTE
                        val = ent.start_date

                    intent.filters.append(FilterClause(
                        entity="project",
                        parameter=param,
                        operator=op,
                        value=val,
                        source_entity="duckling:time",
                        description=f"{param} {op.value} {val}"
                    ))

            elif ent.dim == "number":
                before_text = prompt_lower[:ent.start]
                if any(w in before_text[-15:] for w in ["top", "first", "limit"]):
                    intent.limit = int(ent.num_value)

    def _map_domain_concepts(self, prompt: str, intent: IntentSchema) -> List[Dict[str, Any]]:
        matched = []
        prompt_lower = prompt.lower()

        # 1. Geographic / Country mapping
        country_found = None
        for code, name in COUNTRY_MAP.items():
            pattern = rf"\b{name.lower()}\b"
            if re.search(pattern, prompt_lower):
                country_found = (code, name)
                break
        
        if not country_found:
            for code in COUNTRY_MAP.keys():
                if re.search(rf"\b{code}\b", prompt):
                    country_found = (code, COUNTRY_MAP[code])
                    break

        if country_found:
            code, name = country_found
            intent.filters.append(FilterClause(
                entity="organization",
                parameter="country",
                operator=Operator.EQ,
                value=code,
                source_entity="domain:country",
                description=f"organization.country = '{code}' ({name})"
            ))
            matched.append({"type": "country", "code": code, "name": name})

        # 2. SME filter
        if re.search(r"\bsme\b|\bsmes\b|small and medium", prompt_lower):
            intent.filters.append(FilterClause(
                entity="organization",
                parameter="SME",
                operator=Operator.EQ,
                value=True,
                source_entity="domain:sme",
                description="organization.SME = TRUE"
            ))
            matched.append({"type": "sme", "value": True})

        # 3. Role filter
        if "coordinator" in prompt_lower:
            intent.filters.append(FilterClause(
                entity="organization",
                parameter="role",
                operator=Operator.EQ,
                value="coordinator",
                source_entity="domain:role",
                description="organization.role = 'coordinator'"
            ))
            matched.append({"type": "role", "value": "coordinator"})

        # 4. EuroSciVoc & Topic Keywords
        for canonical_topic, aliases in TOPIC_ALIASES.items():
            matched_alias = False
            for alias in aliases:
                pattern = rf"\b{alias}\b"
                if re.search(pattern, prompt_lower):
                    intent.filters.append(FilterClause(
                        entity="euroSciVoc",
                        parameter="euroSciVocTitle",
                        operator=Operator.LIKE,
                        value=f"%{canonical_topic}%",
                        source_entity="domain:euroSciVoc",
                        description=f"euroSciVocTitle LIKE '%{canonical_topic}%'"
                    ))
                    matched.append({"type": "euroSciVoc_topic", "canonical": canonical_topic, "matched_text": alias})
                    matched_alias = True
                    break
            if matched_alias:
                break

        # 5. Funding Scheme mapping
        schemes = ["HORIZON-RIA", "HORIZON-IA", "HORIZON-CSA", "HORIZON-ERC", "HORIZON-MSCA", "ERC", "MSCA"]
        for sch in schemes:
            if sch.lower() in prompt_lower:
                full_sch = sch if sch.startswith("HORIZON-") else f"HORIZON-{sch}"
                intent.filters.append(FilterClause(
                    entity="project",
                    parameter="fundingScheme",
                    operator=Operator.LIKE,
                    value=f"%{full_sch}%",
                    source_entity="domain:fundingScheme",
                    description=f"project.fundingScheme LIKE '%{full_sch}%'"
                ))
                matched.append({"type": "funding_scheme", "value": full_sch})
                break

        return matched

    def _apply_projections_and_ordering(self, intent: IntentSchema):
        if intent.target_entity == "project":
            intent.projections = ["id", "acronym", "title", "startDate", "endDate", "totalCost", "ecMaxContribution", "fundingScheme"]
            if not intent.order_by:
                intent.order_by.append(OrderByClause(entity="project", parameter="totalCost", order=SortOrder.DESC))
        elif intent.target_entity == "organization":
            intent.projections = ["organisationID", "name", "country", "city", "SME", "activityType", "role", "ecContribution", "projectAcronym"]
            if not intent.order_by:
                intent.order_by.append(OrderByClause(entity="organization", parameter="ecContribution", order=SortOrder.DESC))
        elif intent.target_entity == "projectPublications":
            intent.projections = ["id", "title", "journalTitle", "publishedYear", "authors", "doi", "projectAcronym"]
            if not intent.order_by:
                intent.order_by.append(OrderByClause(entity="projectPublications", parameter="publishedYear", order=SortOrder.DESC))
        elif intent.target_entity == "projectDeliverables":
            intent.projections = ["deliverableType", "description", "url", "projectAcronym"]
