"""
GCAIP Theme 3 — Reservoir Fill Status Processor

Algorithm: JRC Monthly Water History + Sentinel-1 water extent
Computes fill fraction, trend, days to full/empty, spillway risk.
"""
import structlog
from datetime import date, datetime, timedelta, timezone

import ee

from gee import client as gee_client
from gee.processors.base import BaseThemeProcessor, ThemeResult

log = structlog.get_logger(__name__)

VIS_RESERVOIR = {
    "min": 0,
    "max": 1,
    "palette": ["#d4e6f1", "#1a5276"],  # Light → dark blue for water depth proxy
}


class ReservoirProcessor(BaseThemeProcessor):
    THEME_NAME = "reservoir"

    def compute(
        self, aoi_geojson: dict, date_range: tuple[str, str]
    ) -> ThemeResult:
        start_date, end_date = date_range
        aoi = self.get_aoi_geometry(aoi_geojson)
        try:
            return gee_client.safe_call(
                self._run_gee_analysis, aoi, start_date, end_date
            )
        except Exception as exc:
            log.error("reservoir.compute_error", error=str(exc))
            return ThemeResult.error_result(self.THEME_NAME, str(exc))

    def _run_gee_analysis(
        self, aoi: "ee.Geometry", start_date: str, end_date: str
    ) -> ThemeResult:
        end = date.fromisoformat(end_date)

        # ── Current water extent from Sentinel-1 ────────────────────────────
        s1 = (
            ee.ImageCollection("COPERNICUS/S1_GRD")
            .filterBounds(aoi)
            .filterDate(start_date, end_date)
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .select("VV")
        )

        s1_count = s1.size().getInfo()
        if s1_count == 0:
            # Fall back to JRC monthly history only
            confidence = 0.5
            current_water = (
                ee.ImageCollection("JRC/GSW1_4/MonthlyHistory")
                .filterBounds(aoi)
                .filter(ee.Filter.calendarRange(end.month, end.month, "month"))
                .sort("system:time_start", False)
                .first()
                .eq(2)  # 2 = permanent water in JRC
                .unmask(0)
            )
        else:
            confidence = min(1.0, 0.6 + s1_count * 0.1)
            # SAR water detection: VV < -15 dB = open water
            s1_mean = s1.mean().log10().multiply(10)
            current_water = s1_mean.lt(-15.0).rename("water")

        # ── Area statistics ──────────────────────────────────────────────────
        pixel_area_km2 = ee.Image.pixelArea().divide(1e6)
        current_area_stats = gee_client.get_stats(
            image=current_water.multiply(pixel_area_km2).rename("area"),
            aoi=aoi,
            scale=20,
            reducer=ee.Reducer.sum(),
        )
        current_area_km2 = float(current_area_stats.get("area", 0) or 0)

        # ── Historical max area (JRC: maximum observed water extent) ─────────
        jrc_max = (
            ee.Image("JRC/GSW1_4/GlobalSurfaceWater")
            .select("max_extent")
            .multiply(pixel_area_km2)
        )
        max_area_stats = gee_client.get_stats(
            image=jrc_max.rename("area"),
            aoi=aoi,
            scale=30,
            reducer=ee.Reducer.sum(),
        )
        max_area_km2 = float(max_area_stats.get("area", 1) or 1)

        fill_fraction_pct = min(100.0, (current_area_km2 / max_area_km2) * 100.0)

        # ── Same date last year for comparison ───────────────────────────────
        last_year_start = (end.replace(year=end.year - 1) - timedelta(days=15)).isoformat()
        last_year_end = (end.replace(year=end.year - 1) + timedelta(days=15)).isoformat()
        s1_last_year = (
            ee.ImageCollection("COPERNICUS/S1_GRD")
            .filterBounds(aoi)
            .filterDate(last_year_start, last_year_end)
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .select("VV")
        )
        if s1_last_year.size().getInfo() > 0:
            last_year_water = s1_last_year.mean().log10().multiply(10).lt(-15.0)
            ly_stats = gee_client.get_stats(
                image=last_year_water.multiply(pixel_area_km2).rename("area"),
                aoi=aoi, scale=20, reducer=ee.Reducer.sum(),
            )
            last_year_area_km2 = float(ly_stats.get("area", 0) or 0)
            last_year_fill_pct = (last_year_area_km2 / max_area_km2) * 100.0
        else:
            last_year_fill_pct = None

        # ── Trend: compute fill change over past 30 days ─────────────────────
        start_30d = (end - timedelta(days=30)).isoformat()
        s1_30d_ago = (
            ee.ImageCollection("COPERNICUS/S1_GRD")
            .filterBounds(aoi)
            .filterDate(start_30d, (end - timedelta(days=25)).isoformat())
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .select("VV")
        )
        if s1_30d_ago.size().getInfo() > 0:
            water_30d_ago = s1_30d_ago.mean().log10().multiply(10).lt(-15.0)
            ago_stats = gee_client.get_stats(
                image=water_30d_ago.multiply(pixel_area_km2).rename("area"),
                aoi=aoi, scale=20, reducer=ee.Reducer.sum(),
            )
            area_30d_ago = float(ago_stats.get("area", 0) or 0)
            fill_30d_ago = (area_30d_ago / max_area_km2) * 100.0
            rate_pct_per_day = (fill_fraction_pct - fill_30d_ago) / 30.0
        else:
            rate_pct_per_day = 0.0

        fill_trend = (
            "FILLING" if rate_pct_per_day > 0.1
            else "DRAINING" if rate_pct_per_day < -0.1
            else "STABLE"
        )

        # Days to full/empty
        days_to_full = None
        days_to_empty = None
        if fill_trend == "FILLING" and rate_pct_per_day > 0:
            days_to_full = int((100.0 - fill_fraction_pct) / rate_pct_per_day)
        elif fill_trend == "DRAINING" and rate_pct_per_day < 0:
            days_to_empty = int(fill_fraction_pct / abs(rate_pct_per_day))

        # Spillway risk
        spillway_risk = self._spillway_risk(fill_fraction_pct, rate_pct_per_day)

        # Tile URL
        tile_url, expires_at = gee_client.get_tile_url(current_water.clip(aoi), VIS_RESERVOIR)

        anomaly_score = max(0.0, (fill_fraction_pct - 70.0) / 30.0 * 100.0)  # spikes above 70%

        metric_label = (
            f"Reservoir {fill_fraction_pct:.0f}% full"
            + (f" (last year: {last_year_fill_pct:.0f}%)" if last_year_fill_pct else "")
        )

        return ThemeResult(
            theme=self.THEME_NAME,
            tile_url=tile_url,
            tile_url_expires_at=expires_at,
            vis_params=VIS_RESERVOIR,
            metric_value=fill_fraction_pct,
            metric_unit="%",
            metric_label=metric_label,
            stats={
                "fill_fraction_pct": round(fill_fraction_pct, 1),
                "current_area_km2": round(current_area_km2, 2),
                "max_historical_area_km2": round(max_area_km2, 2),
                "fill_trend": fill_trend,
                "rate_pct_per_day": round(rate_pct_per_day, 3),
                "days_to_full": days_to_full,
                "days_to_empty": days_to_empty,
                "spillway_risk": spillway_risk,
                "last_year_fill_pct": (
                    round(last_year_fill_pct, 1) if last_year_fill_pct else None
                ),
                "s1_scene_count": s1_count,
            },
            anomaly_score=round(anomaly_score, 1),
            confidence=round(confidence, 2),
            data_age_hours=self.data_age_from_millis(
                s1.sort("system:time_start", False).first()
                .get("system:time_start").getInfo()
                if s1_count > 0 else None
            ),
            data_source=f"Sentinel-1 GRD + JRC GSW 1.4, {end_date}",
            error=None,
        )

    @staticmethod
    def _spillway_risk(fill_pct: float, rate: float) -> str:
        if fill_pct >= 95:
            return "CRITICAL"
        if fill_pct >= 88 and rate > 0.2:
            return "HIGH"
        if fill_pct >= 80:
            return "MEDIUM"
        if fill_pct >= 70:
            return "LOW-MEDIUM"
        return "LOW"
