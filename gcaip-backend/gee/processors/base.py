"""
Abstract base class for all GEE theme processors.

Every theme processor MUST:
  - Implement compute() → ThemeResult
  - Return confidence (0-1) and data_age_hours on every call
  - Handle the no-images case gracefully (return error ThemeResult, don't raise)
  - Include tile_url + vis_params for map display
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import ee

from gee import client as gee_client


@dataclass
class ThemeResult:
    """
    Universal return type for all GEE theme processors.
    Frontend consumes this directly after enrichment.
    """
    theme: str
    tile_url: str
    tile_url_expires_at: datetime
    vis_params: dict

    metric_value: float
    metric_unit: str
    metric_label: str

    stats: dict
    anomaly_score: float   # 0-100
    confidence: float      # 0-1
    data_age_hours: float
    data_source: str

    error: str | None = None
    # 'transient'      → retry may succeed (missing data, quota exceeded)
    # 'not_applicable' → this theme does not apply to this AOI geometry
    # 'data_gap'       → data genuinely absent for this region/date (no retry benefit)
    # None             → success
    error_class: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dict for SSE and DB storage."""
        return {
            "theme": self.theme,
            "tile_url": self.tile_url,
            "tile_url_expires_at": self.tile_url_expires_at.isoformat()
            if self.tile_url_expires_at else None,
            "vis_params": self.vis_params,
            "metric_value": self.metric_value,
            "metric_unit": self.metric_unit,
            "metric_label": self.metric_label,
            "stats": self.stats,
            "anomaly_score": self.anomaly_score,
            "confidence": self.confidence,
            "data_age_hours": self.data_age_hours,
            "data_source": self.data_source,
            "error": self.error,
            "error_class": self.error_class,
        }

    @classmethod
    def error_result(
        cls,
        theme: str,
        error_message: str,
        error_class: str = "transient",
    ) -> "ThemeResult":
        """Construct a failed ThemeResult — all fields valid, error non-null."""
        from datetime import timezone
        return cls(
            theme=theme,
            tile_url="",
            tile_url_expires_at=datetime.now(timezone.utc),
            vis_params={},
            metric_value=0.0,
            metric_unit="",
            metric_label="Data unavailable",
            stats={},
            anomaly_score=0.0,
            confidence=0.0,
            data_age_hours=999.0,
            data_source="Error",
            error=error_message,
            error_class=error_class,
        )

    @classmethod
    def not_applicable_result(
        cls,
        theme: str,
        reason: str,
    ) -> "ThemeResult":
        """Construct a not-applicable ThemeResult for AOI geometry mismatches.
        
        Use when the theme fundamentally cannot apply to the given AOI
        (e.g. coastal_outfall on an inland AOI), rather than a transient
        data-availability issue that a retry might fix.
        """
        from datetime import timezone
        return cls(
            theme=theme,
            tile_url="",
            tile_url_expires_at=datetime.now(timezone.utc),
            vis_params={},
            metric_value=0.0,
            metric_unit="",
            metric_label="Not applicable to this AOI",
            stats={},
            anomaly_score=0.0,
            confidence=0.0,
            data_age_hours=0.0,
            data_source="N/A",
            error=reason,
            error_class="not_applicable",
        )


class BaseThemeProcessor(ABC):
    """
    Abstract base for all GCAIP GEE theme processors.
    Subclasses implement compute() with full GEE logic.
    """

    THEME_NAME: str = ""  # Override in each subclass

    def __init__(self) -> None:
        # Ensure GEE is initialized for this process
        gee_client.initialize()

    @abstractmethod
    def compute(self, aoi_geojson: dict, date_range: tuple[str, str]) -> ThemeResult:
        """
        Execute the GEE analysis for this theme.

        Args:
            aoi_geojson: GeoJSON dict (Feature or Geometry) representing the AOI
            date_range: (start_date_str, end_date_str) in YYYY-MM-DD format

        Returns:
            ThemeResult with tile_url, stats, confidence, etc.
            On error: ThemeResult.error_result(theme, message) — never raise from here.
        """

    def get_aoi_geometry(self, aoi_geojson: dict) -> "ee.Geometry":
        """Convert GeoJSON AOI dict to ee.Geometry."""
        return gee_client.geojson_to_ee_geometry(aoi_geojson)

    def get_reference_period(
        self, end_date: str, years_back: int = 3
    ) -> tuple[str, str]:
        """
        Compute a same-season reference period N years back.
        Used to build climatological baselines for anomaly scoring.

        Args:
            end_date: ISO date string (YYYY-MM-DD) — the current analysis end
            years_back: How many years to look back

        Returns:
            (ref_start, ref_end) in YYYY-MM-DD format
        """
        from datetime import date, timedelta
        end = date.fromisoformat(end_date)
        ref_end = end.replace(year=end.year - years_back)
        ref_start = (ref_end - timedelta(days=30)).isoformat()
        return ref_start, ref_end.isoformat()

    def apply_s2_cloud_mask(
        self, image: "ee.Image"
    ) -> "ee.Image":
        """
        Sentinel-2 cloud masking using the Scene Classification Layer (SCL).
        SCL values 4 (vegetation) and 5 (bare soil) are kept; everything
        else (cloud, cloud shadow, snow, water) is masked out.
        """
        scl = image.select("SCL")
        # Keep: vegetation(4), bare soil(5), built-up(6)
        cloud_free = scl.gte(4).And(scl.lte(6))
        return image.updateMask(cloud_free)

    def compute_anomaly_score(
        self,
        current_value: float,
        historical_mean: float,
        historical_std: float,
    ) -> float:
        """
        Compute a 0-100 anomaly score using z-score mapping.
        z=0 → score=0; z=±3 → score≈100
        """
        if historical_std == 0:
            return 0.0
        z = abs(current_value - historical_mean) / historical_std
        # Sigmoid-like mapping: 3σ → ~95
        score = min(100.0, (z / 3.0) * 100.0)
        return round(score, 1)

    def data_age_from_millis(self, millis: float | None) -> float:
        """Convert GEE image timestamp (milliseconds since epoch) to age in hours."""
        if millis is None:
            return 999.0
        from datetime import timezone
        import time
        now_ms = time.time() * 1000
        return round((now_ms - millis) / (3600 * 1000), 1)
