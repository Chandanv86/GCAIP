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
        Try IMERG V07 first, fall back to V06, then ERA5-Land, then GSMaP v8.
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

        # JAXA GSMaP v8 — free, ~4hr NRT latency, 0.1° resolution
        gsmap = (
            ee.ImageCollection("JAXA/GPM_L3/GSMaP/v8/operational")
            .filterBounds(aoi)
            .filterDate(start, end)
            .select("hourlyPrecipRateGC")
            .map(lambda img: img.rename("precipitation"))
        )
        if gsmap.size().getInfo() > 0:
            return gsmap, "GSMaP v8 (JAXA)"

        return ee.ImageCollection([]), "none"


    def _run_gee_analysis(
        self, aoi: "ee.Geometry", start_date: str, end_date: str
    ) -> ThemeResult:
        end = date.fromisoformat(end_date)
        start_7d = (end - timedelta(days=7)).isoformat()
        start_30d = (end - timedelta(days=30)).isoformat()

        # ── GPM IMERG / Fallbacks: accumulate precipitation ──────────────────
        imerg, precip_source = self._get_precip_collection(aoi, start_30d, end_date)

        # ── Auto-date-shift: if data is stale, adjust window to latest data ──
        date_shifted = False
        if precip_source != "none":
            try:
                latest = imerg.sort("system:time_start", False).first()
                latest_ts = latest.get("system:time_start").getInfo()
                if latest_ts:
                    latest_dt = datetime.fromtimestamp(latest_ts / 1000, tz=timezone.utc)
                    data_end = latest_dt.date()
                    gap_days = (end - data_end).days
                    if gap_days > 3:
                        log.warning(
                            "rainfall.data_stale",
                            gap_days=gap_days,
                            requested_end=end_date,
                            data_available_to=data_end.isoformat(),
                            source=precip_source,
                        )
                        # Shift analysis window to match actual data availability
                        end = data_end
                        end_date = end.isoformat()
                        start_7d = (end - timedelta(days=7)).isoformat()
                        start_30d = (end - timedelta(days=30)).isoformat()
                        date_shifted = True
            except Exception as shift_exc:
                log.warning("rainfall.date_shift_error", error=str(shift_exc))

        def accum_mm(start: str, stop: str) -> float:
            col = imerg.filterDate(start, stop)
            if col.size().getInfo() == 0:
                return 0.0
            # IMERG/GSMaP: mm/hr × 0.5hr per 30min step = mm
            # ERA5: already in mm after *1000 conversion
            if "IMERG" in precip_source or "GSMaP" in precip_source:
                multiplier = 0.5
            else:
                multiplier = 1.0
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

        # Guard: fail if no data at all (even after date shift)
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
            tile_url, expires_at = gee_client.get_tile_url(accum_30d_img.clip(aoi), VIS_RAINFALL)
        else:
            tile_url, expires_at = None, None

        # Confidence: based on actual data availability (scene count), not rainfall amount.
        # A genuinely dry region with full IMERG coverage should still have high confidence.
        scene_count_7d = imerg.filterDate(start_7d, end_date).size().getInfo()
        if scene_count_7d >= 48 * 5:       # IMERG has ~48 images/day, 5+ days = good coverage
            confidence = 0.90
        elif scene_count_7d >= 48 * 2:     # 2+ days
            confidence = 0.75
        elif scene_count_7d > 0:           # Some data
            confidence = 0.60
        else:
            confidence = 0.35              # No satellite observations at all
        if date_shifted:
            confidence = max(0.35, confidence - 0.10)  # Penalize for stale data

        # Plausibility check: flag results where high-confidence extreme dryness
        # is contradicted by the raw accumulation relative to baseline.
        # If accum_7d is within 70% of the climatological mean yet SPI < -1.5,
        # the SPI is likely driven by a miscalibrated/sparse CHIRPS baseline
        # rather than a genuine drought signal — flag for review.
        plausibility_flag = None
        if (spi_7 < -1.5
                and confidence >= 0.75
                and clim_7d["mean"] > 0
                and accum_7d >= clim_7d["mean"] * 0.7):
            plausibility_flag = (
                f"SPI={spi_7:.2f} (Extremely/Very Dry) but raw 7-day accumulation "
                f"({accum_7d:.1f}mm) is \u226570% of climatological mean "
                f"({clim_7d['mean']:.1f}mm). SPI may be skewed by sparse CHIRPS "
                f"pixels at scale=5500m for this AOI size. Treat with caution."
            )
            # Reduce confidence to reflect correctness risk
            confidence = max(0.35, confidence - 0.20)
            log.warning(
                "rainfall.plausibility_mismatch",
                spi_7=spi_7,
                accum_7d=accum_7d,
                chirps_mean=clim_7d["mean"],
                original_confidence=round(confidence + 0.20, 2),
                adjusted_confidence=round(confidence, 2),
            )

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
                "date_shifted": date_shifted,           # flag for UI transparency
                "analysis_end_date": end_date,          # actual date used (may differ from request)
                "plausibility_flag": plausibility_flag,  # None or warning string
            },
            anomaly_score=round(anomaly_score, 1),
            confidence=round(confidence, 2),
            data_age_hours=actual_data_age_hours,
            # Include the ACTUAL end_date used in data_source string, not the
            # originally requested date. date_shifted=True means these differ.
            data_source=f"{precip_source} (NRT) + CHIRPS 1981-2020 baseline, analysis_end={end_date}{' [date-shifted from requested]' if date_shifted else ''}",
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
        Compute the N-day accumulated precipitation baseline from CHIRPS.

        For each year in the 1991-2020 baseline, sums CHIRPS daily values over
        the exact N-day window ending on the same calendar date as ref_date.
        Then takes mean and std of those ~30 annual N-day totals.

        This is the correct SPI approach: comparing an N-day accumulation
        (from GPM) against an N-day accumulated climatology (from CHIRPS).
        The previous implementation took a ±15-day DOY daily mean and scaled
        by N, which overestimated the baseline (e.g. daily mean 12mm/day × 7
        = 84mm baseline, vs actual 7-day total of ~40mm → wrong SPI sign).
        """
        from datetime import timedelta as _td

        BASELINE_YEARS = list(range(1991, 2021))  # 30-year WMO standard period

        # Window: [ref_date - N days, ref_date] for each baseline year
        # Build a per-year summed image collection server-side via mapped filter+sum
        def _year_sum(yr: int) -> "ee.Image":
            yr_ref = ref_date.replace(year=yr)
            yr_start = (yr_ref - _td(days=days)).isoformat()
            yr_end = yr_ref.isoformat()
            return (
                chirps
                .filterDate(yr_start, yr_end)
                .select("precipitation")
                .sum()
                .set("year", yr)
            )

        year_sums = ee.ImageCollection(
            [_year_sum(yr) for yr in BASELINE_YEARS]
        )

        # Count usable years (some early years may have sparse CHIRPS coverage)
        scene_count = gee_client.safe_call(year_sums.size().getInfo)
        if scene_count < 5:
            return {"mean": 0.0, "std": 1.0, "scene_count": 0}

        # Server-side mean and std of the per-year N-day totals
        mean_img = year_sums.mean()
        variance_img = year_sums.map(
            lambda img: img.subtract(mean_img).pow(2)
        ).mean()

        stats = gee_client.get_stats(
            image=mean_img.rename("mean").addBands(
                variance_img.sqrt().rename("std")
            ),
            aoi=aoi,
            scale=5500,  # CHIRPS native ~5.5km
            reducer=ee.Reducer.mean(),
        )

        mean_val = float(stats.get("mean", 0) or 0)
        std_val = float(stats.get("std", 0.1) or 0.1)

        return {
            "mean": mean_val,
            # Floor: at least 20% of mean or 1mm — prevents SPI blowing up in
            # near-zero-variance hyper-arid zones.
            "std": max(std_val, mean_val * 0.20, 1.0),
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
