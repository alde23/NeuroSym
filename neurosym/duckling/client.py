"""Typed Duckling entity extraction client."""

import logging
import os
from typing import Any, Dict, List, Optional
import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_DUCKLING_URL = os.environ.get("DUCKLING_URL", "http://localhost:8005/parse")


class DucklingTimeValue(BaseModel):
    value: Optional[str] = None
    grain: Optional[str] = None


class DucklingAmountValue(BaseModel):
    value: Optional[float] = None
    unit: Optional[str] = None


class DucklingDurationValue(BaseModel):
    value: Optional[float] = None
    unit: Optional[str] = None
    normalized_value: Optional[float] = None


class ExtractedEntity(BaseModel):
    """Normalized structured entity extracted by Duckling."""
    dim: str  # 'time', 'amount-of-money', 'number', 'duration', 'ordinal'
    body: str
    start: int
    end: int
    latent: bool = False
    
    # Typed extracted values
    val_type: str = "value"  # 'value' or 'interval'
    
    # For numeric/amount
    num_value: Optional[float] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    currency: Optional[str] = "EUR"
    
    # For temporal
    start_date: Optional[str] = None  # YYYY-MM-DD
    end_date: Optional[str] = None    # YYYY-MM-DD
    grain: Optional[str] = None
    
    # For duration
    duration_val: Optional[float] = None
    duration_unit: Optional[str] = None
    
    # Raw value dictionary from Duckling
    raw_value: Dict[str, Any] = Field(default_factory=dict)


class DucklingClient:
    """Client for querying the Duckling Haskell/Rasa REST API."""

    def __init__(self, endpoint_url: str = DEFAULT_DUCKLING_URL, timeout: float = 5.0):
        self.endpoint_url = endpoint_url
        self.timeout = timeout

    def extract_entities(self, text: str, dims: Optional[List[str]] = None, tz: str = "UTC") -> List[ExtractedEntity]:
        """Extracts probabilistic typed entities from text using Duckling."""
        if not dims:
            dims = ["time", "amount-of-money", "number", "duration", "ordinal"]

        payload = {
            "text": text,
            "dims": str(dims).replace("'", '"'),
            "tz": tz,
            "locale": "en_GB",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(self.endpoint_url, data=payload)
                response.raise_for_status()
                raw_data = response.json()
        except httpx.HTTPError as e:
            logger.error(f"Duckling request failed: {e}")
            raise RuntimeError(
                f"Failed to connect to Duckling server at {self.endpoint_url}. "
                f"Ensure docker container 'duckling-server' is running."
            ) from e

        entities: List[ExtractedEntity] = []
        for item in raw_data:
            entity = self._normalize_item(item)
            if entity:
                entities.append(entity)

        return entities

    def _normalize_item(self, item: Dict[str, Any]) -> Optional[ExtractedEntity]:
        dim = item.get("dim")
        body = item.get("body", "")
        start = item.get("start", 0)
        end = item.get("end", 0)
        latent = item.get("latent", False)
        val_data = item.get("value", {})
        val_type = val_data.get("type", "value")

        entity = ExtractedEntity(
            dim=dim,
            body=body,
            start=start,
            end=end,
            latent=latent,
            val_type=val_type,
            raw_value=val_data
        )

        if dim == "amount-of-money":
            if val_type == "interval":
                from_part = val_data.get("from", {})
                to_part = val_data.get("to", {})
                if from_part:
                    entity.min_amount = float(from_part.get("value", 0))
                    entity.currency = from_part.get("unit", "EUR")
                if to_part:
                    entity.max_amount = float(to_part.get("value", 0))
                    entity.currency = to_part.get("unit", "EUR")
            else:
                entity.num_value = float(val_data.get("value", 0))
                entity.currency = val_data.get("unit", "EUR")

        elif dim == "time":
            if val_type == "interval":
                from_part = val_data.get("from", {})
                to_part = val_data.get("to", {})
                if from_part and "value" in from_part:
                    entity.start_date = str(from_part["value"])[:10]
                    entity.grain = from_part.get("grain")
                if to_part and "value" in to_part:
                    entity.end_date = str(to_part["value"])[:10]
                    entity.grain = to_part.get("grain")
            else:
                val = val_data.get("value")
                if val:
                    iso_date = str(val)[:10]
                    entity.start_date = iso_date
                    entity.grain = val_data.get("grain")

        elif dim == "number":
            entity.num_value = float(val_data.get("value", 0))

        elif dim == "duration":
            entity.duration_val = float(val_data.get("value", 0))
            entity.duration_unit = val_data.get("unit", "")

        return entity
