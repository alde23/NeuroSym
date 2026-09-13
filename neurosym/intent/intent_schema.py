"""Intent Schema representing a validated, executable query intent over the Master Schema."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Operator(str, Enum):
    EQ = "="
    NEQ = "!="
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    BETWEEN = "BETWEEN"
    IN = "IN"
    LIKE = "LIKE"
    CONTAINS = "CONTAINS"
    IS_TRUE = "IS_TRUE"
    IS_FALSE = "IS_FALSE"


class FilterClause(BaseModel):
    """A single deterministic filter constraint mapped to a master schema parameter."""
    entity: str
    parameter: str
    operator: Operator
    value: Any
    value_to: Optional[Any] = None
    source_entity: Optional[str] = None  # e.g. 'duckling:time', 'duckling:amount-of-money', 'domain:country'
    description: Optional[str] = None


class SortOrder(str, Enum):
    ASC = "ASC"
    DESC = "DESC"


class OrderByClause(BaseModel):
    entity: str
    parameter: str
    order: SortOrder = SortOrder.DESC


class Aggregation(BaseModel):
    func: str  # COUNT, SUM, AVG, MIN, MAX
    entity: str
    parameter: Optional[str] = None
    alias: str


class IntentSchema(BaseModel):
    """
    A formal, validated subset and specialization of the Master Schema.
    Encapsulates the structured query intent derived from Duckling and domain entities.
    """
    target_entity: str = "project"
    prompt: str = ""
    filters: List[FilterClause] = Field(default_factory=list)
    projections: List[str] = Field(default_factory=list)
    aggregations: List[Aggregation] = Field(default_factory=list)
    order_by: List[OrderByClause] = Field(default_factory=list)
    limit: int = 20
    offset: int = 0
    extracted_duckling_entities: List[Dict[str, Any]] = Field(default_factory=list)
    matched_domain_entities: List[Dict[str, Any]] = Field(default_factory=list)
