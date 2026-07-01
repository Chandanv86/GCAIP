"""
Pydantic request/response schemas for the AOI endpoints.
"""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AOICreateRequest(BaseModel):
    geojson: dict = Field(
        ...,
        description="GeoJSON Feature, FeatureCollection, or Geometry (Polygon/MultiPolygon)",
    )
    name: str | None = Field(None, max_length=512)

    @field_validator("geojson")
    @classmethod
    def validate_geojson(cls, v: dict) -> dict:
        allowed = {"Feature", "FeatureCollection", "Polygon", "MultiPolygon"}
        geo_type = v.get("type", "")
        if geo_type not in allowed:
            raise ValueError(f"GeoJSON type must be one of {allowed}, got '{geo_type}'")
        return v


class AOIResponse(BaseModel):
    aoi_id: uuid.UUID
    name: str | None
    area_km2: float | None
    country_code: str | None
    admin_level1: str | None
    admin_level2: str | None
    created_at: datetime
    geojson: dict | None = None

    model_config = {"from_attributes": True}


class AOIListResponse(BaseModel):
    items: list[AOIResponse]
    total: int
    page: int
    page_size: int
