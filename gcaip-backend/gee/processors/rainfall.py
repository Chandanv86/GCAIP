"""
GCAIP Theme 2 — Rainfall Anomaly Processor

Algorithm: GPM IMERG accumulation vs CHIRPS 1981-2020 climatology
Data: NASA/GPM_L3/IMERG_V06 + UCSB-CHC/CHIRPS/DAILY

Outputs SPI (Standardized Precipitation Index) at 7-day and 30-day timescales.
Identifies flash-flood risk from high-intensity 30-min IMERG rates.
"""
import structlog
from datetime import date, datetime, timedelta, timezone

import ee

from gee import client as gee_client
from gee.processors.base import BaseThemeProcessor, ThemeResult

log = structlog.get_logger(__name__)

VIS_RAINFALL = {
    "min": 0,
    "max": 500,
    "palette": [
        "#8B4513",  # very dry (brown)
        "#D2691E",
        "#F5DEB3",  # near normal (wheat)
        "#FFFFFF",
        "#ADD8E6",  # wet (light blue)
        "#1E90FF",
        "#00008B",  # very wet (dark blue)
    ],
}


class RainfallProcessor(BaseThemeProcessor):
    """GPM IMERG vs CHIRPS climatology — rainfall anomaly and SPI."""

    THEME_NAME = "rainfall"

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
            log.error("rainfall.compute_error", error=str(exc))
            return ThemeResult.error_result(self.THEME_NAME, str(exc))

    def _get_precip_collection(
        self, aoi: "ee.Geometry", start: str, end: str
    ) -> tuple["ee.ImageCollection", str]:
        """
        Try IMERG V07 first, fall back to V06, then ERA5-Land.
        Returns (collection, source_name).
        """
        # Try IMERG V07 (most current on GEE, updated ~4hr lag)
        v07 = (
            ee.ImageCollection("NASA/GPM_L3/IMERG_V07")
            .filterBounds(aoi)
            .filterDate(start, end)
            .select("precipitation")
        )
        if v07.size().getInfo() > 0:
            return v07, "GPM IMERG V07"

        # Try IMERG V06
        v06 = (
            ee.ImageCollection("NASA/GPM_L3/IMERG_V06")
            .filterBounds(aoi)
            .filterDate(start, end)
            .select("precipitationCal")
            .map(lambda img: img.rename("precipitation"))
        )
        if v06.size().getInfo() > 0:
            return v06, "GPM IMERG V06"

        # ERA5-Land fallback — total_precipitation band, convert m→mm (*1000)
        era5 = (
            ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
            .filterBounds(aoi)
            .filterDate(start, end)
            .select("total_precipitation_sum")
            .map(lambda img: img.multiply(1000).rename("precipitation"))
        )
        if era5.size().getInfo() > 0:
            return era5, "ERA5-Land (ECMWF)"

        return ee.ImageCollection([]), "none"

    def _run_gee_analysis(
        self, aoi: "ee.Geometry", start_date: str, end_date: str
    ) -> ThemeResult:
        end = date.fromisoformat(end_date)
        start_7d = (end - timedelta(days=7)).isoformat()
        start_30d = (end - timedelta(days=30)).isoformat()

        # ── GPM IMERG / Fallbacks: accumulate precipitation ──────────────────
        imerg, precip_source = self._get_precip_collection(aoi, start_30d, end_date)

        def accum_mm(start: str, stop: str) -> float:
            col = imerg.filterDate(start, stop)
            if col.size().getInfo() == 0:
                return 0.0
            # IMERG: mm/hr × 0.5hr per 30min step = mm
            # ERA5: already in mm after *1000 conversion
            multiplier = 0.5 if "IMERG" in precip_source else 1.0
            total = col.map(lambda img: img.multiply(multiplier)).sum()
            stats = gee_client.get_stats(
                image=total, aoi=aoi, scale=11000, reducer=ee.Reducer.mean()
            )
            return float(stats.get("precipitation", 0) or 0)

        accum_7d = accum_mm(start_7d, end_date)
        accum_30d = accum_mm(start_30d, end_date)
        accum_24h = accum_mm(
            (end - timedelta(days=1)).isoformat(), end_date
        )

        # Bug 3 Guard: Minimum precipitation threshold guard
        precip_scene_count = imerg.filterDate(start_7d, end_date).size().getInfo()
        if accum_7d == 0.0 and accum_30d == 0.0 and precip_scene_count == 0:
            raise gee_client.GEEAssetNotFoundError(
                f"No precipitation data available from {precip_source} "
                f"for period {start_30d} to {end_date}. "
                f"Collection may not be updated to this date range yet."
            )

        # Flash flood risk: max 30-min rate in last 7 days
        max_rate_col = imerg.filterDate(start_7d, end_date)
        if max_rate_col.size().getInfo() > 0:
            max_rate_stats = gee_client.get_stats(
                image=max_rate_col.select("precipitation").max(),
                aoi=aoi,
                scale=11000,
                reducer=ee.Reducer.max(),
            )
            max_rate_mm_hr = float(max_rate_stats.get("precipitation", 0) or 0)
        else:
            max_rate_mm_hr = 0.0
        flash_flood_risk = max_rate_mm_hr > 50.0  # IMERG 50mm/hr → flash flood

        # ── CHIRPS climatology (1981-2020 baseline) ───────────────────────────
        # CHIRPS daily: 0.05° resolution, better for 30-day accumulations
        chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
        clim_7d = self._chirps_climatology(chirps, aoi, end, days=7)
        clim_30d = self._chirps_climatology(chirps, aoi, end, days=30)

        # Anomaly: (current - mean) / mean * 100
        anomaly_7d_pct = (
            ((accum_7d - clim_7d["mean"]) / clim_7d["mean"] * 100)
            if clim_7d["mean"] > 0 else 0.0
        )

        # SPI: z-score using historical std
        spi_7 = (
            (accum_7d - clim_7d["mean"]) / clim_7d["std"]
            if clim_7d["std"] > 0 else 0.0
        )
        spi_30 = (
            (accum_30d - clim_30d["mean"]) / clim_30d["std"]
            if clim_30d["std"] > 0 else 0.0
        )

        # SPI classification: > +2.0 = "Extremely Wet"
        spi_label = self._spi_label(spi_7)

        # Percentile rank: where does 7-day total rank historically?
        percentile_7d = self._spi_to_percentile(spi_7)

        # ── Tile URL: 30-day accumulation map ────────────────────────────────
        col_30d = imerg.filterDate(start_30d, end_date)
        if col_30d.size().getInfo() > 0:
            multiplier = 0.5 if "IMERG" in precip_source else 1.0
            accum_30d_img = col_30d.select("precipitation").map(lambda img: img.multiply(multiplier)).sum()
            tile_url, expires_at = gee_client.get_tile_url(accum_30d_img, VIS_RAINFALL)
        else:
            tile_url, expires_at = None, None

        # Confidence: IMERG is near-real-time with ~3hr latency, high confidence
        confidence = 0.85 if accum_7d > 0 else 0.5

        # Anomaly score: |SPI| normalized to 0-100
        anomaly_score = min(100.0, abs(spi_7) / 3.0 * 100.0)

        metric_label = (
            f"{accum_7d:.0f}mm in 7 days (normal: {clim_7d['mean']:.0f}mm, "
            f"{anomaly_7d_pct:+.0f}%)"
        )

        # Bug 6: Compute actual age
        try:
            latest = imerg.sort("system:time_start", False).first()
            latest_ts = latest.get("system:time_start").getInfo()
            actual_data_age_hours = self.data_age_from_millis(latest_ts)
        except Exception:
            actual_data_age_hours = 999.0  # unknown

        return ThemeResult(
            theme=self.THEME_NAME,
            tile_url=tile_url,
            tile_url_expires_at=expires_at,
            vis_params=VIS_RAINFALL,
            metric_value=accum_7d,
            metric_unit="mm",
            metric_label=metric_label,
            stats={
                "accum_24h_mm": round(accum_24h, 1),
                "accum_7d_mm": round(accum_7d, 1),
                "accum_30d_mm": round(accum_30d, 1),
                "chirps_clim_7d_mean_mm": round(clim_7d["mean"], 1),
                "chirps_clim_30d_mean_mm": round(clim_30d["mean"], 1),
                "anomaly_7d_pct": round(anomaly_7d_pct, 1),
                "percentile_7d": round(percentile_7d, 0),
                "spi_7": round(spi_7, 2),
                "spi_30": round(spi_30, 2),
                "spi_label": spi_label,
                "flash_flood_risk": flash_flood_risk,
                "max_30min_rate_mm_hr": round(max_rate_mm_hr, 1),
            },
            anomaly_score=round(anomaly_score, 1),
            confidence=round(confidence, 2),
            data_age_hours=actual_data_age_hours,
            data_source=f"{precip_source} (NRT) + CHIRPS 1981-2020 baseline, {end_date}",
            error=None,
        )

    def _chirps_climatology(
        self,
        chirps: "ee.ImageCollection",
        aoi: "ee.Geometry",
        ref_date: date,
        days: int,
    ) -> dict[str, float]:
        """
        Compute historical mean and std using a SINGLE GEE reduceRegion call.
        Filters CHIRPS by calendar day-of-year window across all baseline 
        years — no Python loop, everything runs server-side in GEE.
        """
        # Get day-of-year window (±15 days around ref_date)
        doy = ref_date.timetuple().tm_yday
        doy_start = max(1, doy - 15)
        doy_end = min(365, doy + 15)

        # Filter entire CHIRPS collection by DOY window, 1991-2020 baseline
        baseline = (
            chirps
            .filter(ee.Filter.date("1991-01-01", "2021-01-01"))
            .filter(ee.Filter.calendarRange(doy_start, doy_end, "day_of_year"))
            .select("precipitation")
        )

        # Count available scenes — if too few, return safe defaults
        scene_count = baseline.size().getInfo()  # 1 call only
        if scene_count < 5:
            return {"mean": 0.0, "std": 1.0, "scene_count": 0}

        # Compute mean and variance composites server-side — single reduceRegion
        mean_img = baseline.mean()
        variance_img = baseline.map(
            lambda img: img.subtract(mean_img).pow(2)
        ).mean()

        # Single reduceRegion call for both mean and variance
        stats = gee_client.get_stats(
            image=mean_img.rename("mean").addBands(
                variance_img.sqrt().rename("std")
            ),
            aoi=aoi,
            scale=5500,  # CHIRPS native ~5.5km
            reducer=ee.Reducer.mean(),
        )

        # Daily mean and standard deviation from GEE
        mean_val_daily = float(stats.get("mean", 0) or 0)
        std_val_daily = float(stats.get("std", 0.1) or 0.1)

        # Scale from daily values to the N-day accumulation window
        mean_val = mean_val_daily * days
        std_val = std_val_daily * (days ** 0.5)

        return {
            "mean": mean_val,
            "std": max(std_val, mean_val * 0.2, 1.0),  # minimum 20% of mean
            "scene_count": scene_count,
        }

    @staticmethod
    def _spi_label(spi: float) -> str:
        if spi >= 2.0:
            return "Extremely Wet"
        elif spi >= 1.5:
            return "Very Wet"
        elif spi >= 1.0:
            return "Moderately Wet"
        elif spi >= -1.0:
            return "Near Normal"
        elif spi >= -1.5:
            return "Moderately Dry"
        elif spi >= -2.0:
            return "Very Dry"
        return "Extremely Dry"

    @staticmethod
    def _spi_to_percentile(spi: float) -> float:
        """Approximate normal CDF → percentile rank from SPI z-score."""
        import math
        return round(50.0 * (1.0 + math.erf(spi / math.sqrt(2))), 1)
