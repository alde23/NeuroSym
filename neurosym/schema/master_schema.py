"""Master Schema models and representation for CORDIS Horizon Europe dataset."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SemanticType(str, Enum):
    NUMBER = "number"
    AMOUNT_OF_MONEY = "amount_of_money"
    DATE = "date"
    DATETIME_INTERVAL = "datetime_interval"
    DURATION = "duration"
    COUNTRY_CODE = "country_code"
    KEYWORD = "keyword"
    TEXT = "text"
    BOOLEAN = "boolean"
    URL = "url"


class DucklingDimension(str, Enum):
    TIME = "time"
    AMOUNT_OF_MONEY = "amount-of-money"
    NUMBER = "number"
    DURATION = "duration"
    ORDINAL = "ordinal"
    NONE = "none"


class ParameterSchema(BaseModel):
    """Represents a single queryable parameter/column within an entity."""
    name: str
    table: str
    column: str
    sql_type: str
    semantic_type: SemanticType
    duckling_dimension: DucklingDimension = DucklingDimension.NONE
    description: str
    unit: Optional[str] = None
    sample_values: List[Any] = Field(default_factory=list)
    vocabulary: Optional[List[str]] = None
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None


class EntitySchema(BaseModel):
    """Represents an entity/table in the CORDIS dataset."""
    name: str
    table_name: str
    description: str
    primary_key: Optional[str] = None
    foreign_keys: Dict[str, str] = Field(default_factory=dict)
    parameters: Dict[str, ParameterSchema] = Field(default_factory=dict)
    row_count: int = 0


class JoinPath(BaseModel):
    """Defines how two entities relate in the database."""
    from_entity: str
    to_entity: str
    join_clause: str


class MasterSchema(BaseModel):
    """The complete master schema cataloging all CORDIS entities, parameters, and vocabularies."""
    version: str = "1.0.0"
    generated_at: Optional[str] = None
    database_file: str = "cordis.duckdb"
    entities: Dict[str, EntitySchema] = Field(default_factory=dict)
    joins: List[JoinPath] = Field(default_factory=list)
    vocabularies: Dict[str, List[str]] = Field(default_factory=dict)

    def get_parameter(self, entity_name: str, param_name: str) -> Optional[ParameterSchema]:
        entity = self.entities.get(entity_name)
        if entity:
            return entity.parameters.get(param_name)
        return None

    def find_parameters_by_dimension(self, dimension: DucklingDimension) -> List[ParameterSchema]:
        results = []
        for entity in self.entities.values():
            for param in entity.parameters.values():
                if param.duckling_dimension == dimension:
                    results.append(param)
        return results
