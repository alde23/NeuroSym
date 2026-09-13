"""Neural Intent Mapper combining Jinja2 prompting, LLM semantic classification, and Guardrails AI validation."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import jinja2

from neurosym.duckling.client import DucklingClient
from neurosym.guardrails.validators import GuardrailsValidator
from neurosym.ingestion.cordis_ingest import DEFAULT_SCHEMA_PATH
from neurosym.intent.intent_schema import FilterClause, IntentSchema, Operator
from neurosym.intent.mapper import IntentMapper
from neurosym.llm.client import LLMClient
from neurosym.schema.master_schema import MasterSchema

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


class NeuralIntentMapper:
    """
    Transforms natural language queries into an IntentSchema using:
    1. Duckling for physical and numeric dimensions.
    2. Jinja2 template formatting with the Master Schema.
    3. LLM semantic operation and intent extraction.
    4. Guardrails AI schema validation to prevent hallucinated columns or operators.
    """

    def __init__(
        self,
        master_schema: Optional[MasterSchema] = None,
        duckling_client: Optional[DucklingClient] = None,
        llm_client: Optional[LLMClient] = None
    ):
        if master_schema is None:
            if DEFAULT_SCHEMA_PATH.exists():
                with open(DEFAULT_SCHEMA_PATH, "r", encoding="utf-8") as f:
                    self.master_schema = MasterSchema.model_validate_json(f.read())
            else:
                self.master_schema = MasterSchema()
        else:
            self.master_schema = master_schema

        self.duckling = duckling_client or DucklingClient()
        self.llm = llm_client or LLMClient()
        self.symbolic_mapper = IntentMapper(master_schema=self.master_schema, duckling_client=self.duckling)

        # Jinja2 environment
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=False
        )

    def parse_and_map(self, prompt: str) -> IntentSchema:
        """Full neural-symbolic intent mapping pipeline."""
        # 1. Extract physical entities with Duckling
        duckling_entities = self.duckling.extract_entities(prompt)

        # 2. Render Jinja2 prompt template
        template = self.jinja_env.get_template("intent_prompt.j2")
        rendered_prompt = template.render(
            schema=self.master_schema,
            duckling_entities=duckling_entities,
            prompt=prompt
        )

        # 3. Predict intent via LLM
        raw_llm_intent = self.llm.generate_json(rendered_prompt)

        # 4. Guardrails AI schema & operator validation
        validation_res = GuardrailsValidator.validate_intent(raw_llm_intent, self.master_schema)
        sanitized = validation_res.sanitized_data or {}

        # 5. Hybrid merge: ensure all symbolic rules (e.g. country codes, topics, amounts) are combined
        symbolic_intent = self.symbolic_mapper.parse_and_map(prompt)

        target_entity = sanitized.get("target_entity", symbolic_intent.target_entity)
        filters: List[FilterClause] = []

        # Add validated LLM filters
        for f in sanitized.get("filters", []):
            filters.append(FilterClause(
                entity=f["entity"],
                parameter=f["parameter"],
                operator=Operator(f["operator"]),
                value=f["value"],
                value_to=f.get("value_to"),
                source_entity="llm:neural_intent",
                description=f.get("description", "")
            ))

        # Add any symbolic filters not already covered
        existing_params = {(f.entity, f.parameter) for f in filters}
        for sf in symbolic_intent.filters:
            if (sf.entity, sf.parameter) not in existing_params:
                filters.append(sf)

        return IntentSchema(
            target_entity=target_entity,
            prompt=prompt,
            filters=filters,
            projections=symbolic_intent.projections,
            order_by=symbolic_intent.order_by,
            limit=sanitized.get("limit", symbolic_intent.limit),
            extracted_duckling_entities=[e.model_dump() for e in duckling_entities],
            matched_domain_entities=symbolic_intent.matched_domain_entities
        )
