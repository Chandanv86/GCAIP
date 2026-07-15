"""Pydantic schemas for analysis trigger + status + results endpoints."""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

# VALID_THEMES is the canonical theme list -- defined once in services/theme_registry.py.
# Import from there; do NOT redeclare it here.
from services.theme_registry import VALID_THEMES  # noqa: F401 (re-exported for callers)


class AnalyzeRequest(BaseModel):
    aoi_id: uuid.UUID
    date_range: dict | None = Field(
        None,
        description='{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}. Defaults to last 30 days.',
    )
    themes: list[str] | None = Field(
        None,
        description="Subset of themes to run. Defaults to all 7.",
    )

    def get_date_range(self) -> tuple[str, str]:
        if self.date_range:
            return self.date_range["start"], self.date_range["end"]
        from datetime import timedelta
        end = date.today()
        start = end - timedelta(days=30)
        return start.isoformat(), end.isoformat()

    def get_themes(self) -> list[str]:
        return self.themes or VALID_THEMES


class AnalyzeResponse(BaseModel):
    job_id: uuid.UUID         # = run_id
    aoi_id: uuid.UUID
    status: str
    sse_url: str              # Relative URL for SSE stream
    estimated_seconds: int = 60


class RunStatusResponse(BaseModel):
    run_id: uuid.UUID
    status: Literal["pending", "running", "complete", "failed"]
    themes_complete: int
    themes_total: int
    theme_statuses: dict[str, str]   # {"flood": "complete", "rainfall": "running", ...}
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class ThemeResultSchema(BaseModel):
    theme: str
    result_id: uuid.UUID
    status: str
    tile_url: str | None
    tile_url_expires_at: datetime | None
    vis_params: dict | None
    metric_value: float | None
    metric_unit: str | None
    metric_label: str | None
    stats: dict
    enrichment: dict
    anomaly_score: float | None
    confidence: float | None
    data_age_hours: float | None
    data_source: str | None
    error_message: str | None
    error_class: str | None

    model_config = {"from_attributes": True}


class RiskScoreSchema(BaseModel):
    overall_score: float
    overall_label: str
    flood_risk: float | None
    erosion_risk: float | None
    water_stress: float | None
    vegetation_health: float | None
    landuse_pressure: float | None
    cross_insights: list[dict]
    population_in_aoi: int | None
    population_at_risk: int | None
    scored_at: datetime

    model_config = {"from_attributes": True}


class FullResultsResponse(BaseModel):
    run_id: uuid.UUID
    aoi_id: uuid.UUID
    status: str
    risk_score: RiskScoreSchema | None
    themes: dict[str, ThemeResultSchema]
    cross_insights: list[dict]
    date_range_start: date
    date_range_end: date
    completed_at: datetime | None
