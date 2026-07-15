"""
gee/processors/effluent_plume.py

Theme 8: Effluent Discharge Plume Processor.

Detects water-quality anomaly plumes (elevated chlorophyll-a / turbidity signatures
consistent with wastewater, industrial, or agricultural discharge) into inland water
bodies (rivers, lakes, reservoirs).

Follows the same contract as flood.py / reservoir.py / mangrove.py:
    - Inherits BaseThemeProcessor
    - compute() returns a standardized ThemeResult
    - All GEE calls routed through gee_client.safe_call
    - GEEAssetNotFoundError -> graceful ThemeResult.error_result
    - Only zonal stats + tile URL templates ever leave GEE
"""

from __future__ import annotations

import structlog

import ee

from gee import client as gee_client
from gee.client import GEEAssetNotFoundError, GEEQuotaError
from gee.processors.base import BaseThemeProcessor, ThemeResult
from services.adaptive_thresholds import self_relative_anomaly_mask

log = structlog.get_logger(__name__)

# Visualization: green (clean) -> dark brown/red (high turbidity/chlorophyll anomaly)
VIS_PLUME = {
    "min": 0,
    "max": 1,
    "palette": [
        "#1a9850",
        "#91cf60",
        "#d9ef8b",
        "#fee08b",
        "#fc8d59",
        "#67001f",
    ],
}

NDCI_THRESHOLD = 0.05
NDTI_THRESHOLD = 0.10
MNDWI_THRESHOLD = 0.1
CLOUD_COVER_MAX = 35
WINDOW_DAYS_FALLBACK_LANDSAT = 30


class EffluentPlumeProcessor(BaseThemeProcessor):
    """Detects and sizes effluent/eutrophication plumes in inland water bodies."""

    THEME_NAME = "effluent_plume"

    def compute(self, aoi_geojson: dict, date_range: tuple[str, str]) -> ThemeResult:
        start, end = date_range
        try:
            aoi = self.get_aoi_geometry(aoi_geojson)
            return self._run_gee_analysis(aoi, start, end)
        except GEEAssetNotFoundError as exc:
            log.info("effluent_plume.no_data", reason=str(exc))
            return ThemeResult.error_result(
                self.THEME_NAME, f"No usable imagery found for the requested window: {exc}"
            )
        except GEEQuotaError as exc:
            log.warning("effluent_plume.quota_exceeded", reason=str(exc))
            return ThemeResult.error_result(self.THEME_NAME, f"GEE quota exceeded: {exc}")
        except Exception as exc:  # noqa: BLE001 - final safety net, never raise to Celery
            log.exception("effluent_plume.unexpected_error")
            return ThemeResult.error_result(self.THEME_NAME, f"Unexpected error: {exc}")

    # ------------------------------------------------------------------
    def _run_gee_analysis(self, aoi: "ee.Geometry", start: str, end: str) -> ThemeResult:
        collection, source_label, scale, cloud_threshold_used = self._load_optical_collection(aoi, start, end)

        image_count = gee_client.safe_call(collection.size().getInfo)
        if image_count == 0:
            raise GEEAssetNotFoundError(
                "No cloud-free optical scenes available across primary/fallback collections"
            )

        current = self._build_composite(collection)

        mndwi = current.normalizedDifference(["B3", "B11"]).rename("mndwi")
        water_mask = mndwi.gt(MNDWI_THRESHOLD)

        ndci = current.normalizedDifference(["B5", "B4"]).rename("ndci")
        ndti = current.normalizedDifference(["B4", "B3"]).rename("ndti")

        plume_mask_fixed = ndci.gt(NDCI_THRESHOLD).And(ndti.gt(NDTI_THRESHOLD)).And(water_mask)

        # Additive: OR in a self-relative (AOI-specific-percentile) NDTI mask so
        # naturally high-baseline rivers (Sundarbans-style) can still detect a real
        # local discharge without raising the fixed global threshold.
        # This NEVER replaces the fixed-threshold mask — only adds to it.
        relative_ndti_mask = self_relative_anomaly_mask(
            ndti, "ndti", aoi, water_mask,
            baseline_percentile=50, anomaly_percentile=90, scale=10,
        )
        if relative_ndti_mask is not None:
            plume_mask = plume_mask_fixed.Or(relative_ndti_mask).And(water_mask)
            relative_triggered = True
        else:
            plume_mask = plume_mask_fixed
            relative_triggered = False

        # --- Baseline (prior-year seasonal composite, same sensor) ---
        ref_start, ref_end = self.get_reference_period(end, years_back=1)
        baseline_collection = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(aoi)
            .filterDate(ref_start, ref_end)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", CLOUD_COVER_MAX))
            .map(self.apply_s2_cloud_mask)
        )
        baseline_count = gee_client.safe_call(baseline_collection.size().getInfo)
        baseline_available = baseline_count > 0
        if baseline_available:
            baseline_img = baseline_collection.median()
            baseline_ndci = baseline_img.normalizedDifference(["B5", "B4"]).rename("ndci_base")
            baseline_ndti = baseline_img.normalizedDifference(["B4", "B3"]).rename("ndti_base")
        else:
            baseline_ndci = ee.Image.constant(0).rename("ndci_base")
            baseline_ndti = ee.Image.constant(0).rename("ndti_base")

        pixel_area_km2 = ee.Image.pixelArea().divide(1e6)

        stats_image = ee.Image.cat(
            [
                pixel_area_km2.updateMask(plume_mask).rename("plume_area_km2"),
                pixel_area_km2.updateMask(water_mask).rename("water_area_km2"),
                ndci.rename("ndci_mean"),
                ndti.rename("ndti_mean"),
                baseline_ndci,
                baseline_ndti,
            ]
        )

        reducer = (
            ee.Reducer.sum()
            .forEach(["plume_area_km2", "water_area_km2"])
            if hasattr(ee.Reducer.sum(), "forEach")
            else ee.Reducer.sum()
        )
        # Combine sum (areas) and mean (indices) reducers explicitly per-band via separate calls
        # to keep behavior predictable across ee API versions.
        area_stats = gee_client.get_stats(
            image=stats_image.select(["plume_area_km2", "water_area_km2"]),
            aoi=aoi,
            scale=10,
            reducer=ee.Reducer.sum(),
            max_pixels=1e10,
        )
        index_stats = gee_client.get_stats(
            image=stats_image.select(["ndci_mean", "ndti_mean", "ndci_base", "ndti_base"]),
            aoi=aoi,
            scale=10,
            reducer=ee.Reducer.mean(),
            max_pixels=1e10,
        )

        plume_area_km2 = float(area_stats.get("plume_area_km2") or 0.0)
        water_area_km2 = float(area_stats.get("water_area_km2") or 0.0)
        ndci_mean = float(index_stats.get("ndci_mean") or 0.0)
        ndti_mean = float(index_stats.get("ndti_mean") or 0.0)
        ndci_base = float(index_stats.get("ndci_base") or 0.0)
        ndti_base = float(index_stats.get("ndti_base") or 0.0)

        # aggregate_max returns a lazy ee.ComputedObject (in real GEE) that must be
        # resolved via .getInfo() before Python arithmetic. In unit test mocks it may
        # already be a plain int/float. Check for the .getInfo attribute defensively.
        latest_millis_obj = gee_client.safe_call(
            collection.aggregate_max, "system:time_start"
        )
        if latest_millis_obj is None:
            latest_millis = None
        elif hasattr(latest_millis_obj, "getInfo"):
            latest_millis = gee_client.safe_call(latest_millis_obj.getInfo)
        else:
            latest_millis = latest_millis_obj  # already a Python scalar
        data_age_hours = self.data_age_from_millis(latest_millis)

        confidence = min(1.0, 0.5 + 0.1 * image_count)
        if source_label != "COPERNICUS/S2_SR_HARMONIZED":
            confidence = max(0.3, confidence - 0.15)  # fallback sensors are coarser

        water_area_safe = max(water_area_km2, 0.01)
        anomaly_score = min(100.0, (plume_area_km2 / water_area_safe) * 300.0)

        tile_url, tile_expires_at = gee_client.get_tile_url(
            plume_mask.selfMask().clip(aoi).visualize(**VIS_PLUME), {}
        )

        return ThemeResult(
            theme=self.THEME_NAME,
            tile_url=tile_url,
            tile_url_expires_at=tile_expires_at,
            vis_params=VIS_PLUME,
            metric_value=round(plume_area_km2, 4),
            metric_unit="km2",
            metric_label="Effluent Plume Extent",
            stats={
                "plume_extent_km2": round(plume_area_km2, 4),
                "water_area_km2": round(water_area_km2, 4),
                "ndci_mean": round(ndci_mean, 4),
                "ndti_mean": round(ndti_mean, 4),
                "ndci_baseline_mean": round(ndci_base, 4),
                "ndti_baseline_mean": round(ndti_base, 4),
                "source_collection": source_label,
                "cloud_threshold_used": cloud_threshold_used,
                "baseline_available": baseline_available,
                "relative_threshold_triggered": relative_triggered,
                "caveats": [
                    "SPM/CDOM proxies use S2 harmonized SR without a secondary "
                    "C2RCC/ACOLITE water-leaving-radiance correction.",
                    "NDCI/NDTI thresholds are generic; site-specific in-situ "
                    "calibration will improve absolute accuracy.",
                ],
            },
            anomaly_score=round(anomaly_score, 2),
            confidence=round(confidence, 2),
            data_age_hours=round(data_age_hours, 2) if data_age_hours is not None else None,
            data_source=source_label,
        )

    # ------------------------------------------------------------------
    def _load_optical_collection(self, aoi: "ee.Geometry", start: str, end: str):
        """Load optical collection with progressive fallback cascade.

        Tier order:
          1. S2 @ default cloud threshold → original date range
          2. S2 @ default → widened +15 days
          3. S2 @ default → widened +30 days
          4. S2 @ relaxed cloud threshold (60%) → original date range
          5. Landsat 8/9 @ default → original date range
          6. Landsat 8/9 → widened +30 days
          7. Sentinel-3 OLCI → original + widened
          8. GEEAssetNotFoundError (all tiers exhausted)

        Returns:
            (collection, source_label, scale, cloud_threshold_used)
        """
        from datetime import date, timedelta

        CLOUD_RELAXED = 60
        start_dt = date.fromisoformat(start)
        end_dt = date.fromisoformat(end)

        def _s2_col(s: str, e: str, cloud_pct: int):
            return (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(aoi)
                .filterDate(s, e)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_pct))
                .map(self.apply_s2_cloud_mask)
            )

        def _landsat_col(s: str, e: str, cloud_pct: int):
            return (
                ee.ImageCollection("LANDSAT/LC09/C02/T1_L2")
                .merge(ee.ImageCollection("LANDSAT/LC08/C02/T1_L2"))
                .filterBounds(aoi)
                .filterDate(s, e)
                .filter(ee.Filter.lt("CLOUD_COVER", cloud_pct))
                .map(self._scale_landsat)
                .select(["SR_B3", "SR_B4", "SR_B5", "SR_B6"], ["B3", "B4", "B5", "B11"])
            )

        # --- Tier 1: S2 @ default cloud, original dates ---
        col = _s2_col(start, end, CLOUD_COVER_MAX)
        cnt = gee_client.safe_call(col.size().getInfo)
        if cnt > 0:
            return col, "COPERNICUS/S2_SR_HARMONIZED", 10, CLOUD_COVER_MAX

        # --- Tier 2: S2 @ default, widened +15 days ---
        w15_start = (start_dt - timedelta(days=15)).isoformat()
        log.info("effluent_plume.fallback_s2_widen_15d", start=w15_start, end=end)
        col = _s2_col(w15_start, end, CLOUD_COVER_MAX)
        cnt = gee_client.safe_call(col.size().getInfo)
        if cnt > 0:
            return col, "COPERNICUS/S2_SR_HARMONIZED", 10, CLOUD_COVER_MAX

        # --- Tier 3: S2 @ default, widened +30 days ---
        w30_start = (start_dt - timedelta(days=30)).isoformat()
        log.info("effluent_plume.fallback_s2_widen_30d", start=w30_start, end=end)
        col = _s2_col(w30_start, end, CLOUD_COVER_MAX)
        cnt = gee_client.safe_call(col.size().getInfo)
        if cnt > 0:
            return col, "COPERNICUS/S2_SR_HARMONIZED", 10, CLOUD_COVER_MAX

        # --- Tier 4: S2 @ relaxed cloud threshold, original dates ---
        log.info("effluent_plume.fallback_s2_relaxed_cloud", threshold=CLOUD_RELAXED)
        col = _s2_col(start, end, CLOUD_RELAXED)
        cnt = gee_client.safe_call(col.size().getInfo)
        if cnt > 0:
            return col, "COPERNICUS/S2_SR_HARMONIZED", 10, CLOUD_RELAXED

        # --- Tier 5: Landsat 8/9 @ default, original dates ---
        log.info("effluent_plume.fallback_landsat")
        col = _landsat_col(start, end, CLOUD_COVER_MAX)
        cnt = gee_client.safe_call(col.size().getInfo)
        if cnt > 0:
            return col, "LANDSAT/LC08+09", 30, CLOUD_COVER_MAX

        # --- Tier 6: Landsat widened +30 days ---
        log.info("effluent_plume.fallback_landsat_widen_30d", start=w30_start, end=end)
        col = _landsat_col(w30_start, end, CLOUD_COVER_MAX)
        cnt = gee_client.safe_call(col.size().getInfo)
        if cnt > 0:
            return col, "LANDSAT/LC08+09", 30, CLOUD_COVER_MAX

        # --- Tier 7: Sentinel-3 OLCI (300m, no cloud filter — coarse backup) ---
        log.info("effluent_plume.fallback_sentinel3")
        col = (
            ee.ImageCollection("COPERNICUS/S3/OLCI")
            .filterBounds(aoi)
            .filterDate(w30_start, end)
            .select(
                ["Oa06_radiance", "Oa08_radiance", "Oa10_radiance", "Oa17_radiance"],
                ["B3", "B4", "B5", "B11"]
            )
        )
        cnt = gee_client.safe_call(col.size().getInfo, retries=5)
        if cnt > 0:
            return col, "COPERNICUS/S3/OLCI", 300, CLOUD_COVER_MAX

        # All 7 tiers exhausted — S2 default/widen/relax, Landsat default/widen, S3
        raise GEEAssetNotFoundError(
            "No cloud-free optical scenes available across all fallback tiers "
            "(S2 default→widen→relax, Landsat default→widen, S3 OLCI)"
        )

    @staticmethod
    def _scale_landsat(image: "ee.Image") -> "ee.Image":
        optical = image.select("SR_B.").multiply(0.0000275).add(-0.2)
        return image.addBands(optical, None, True)

    @staticmethod
    def _build_composite(collection: "ee.ImageCollection") -> "ee.Image":
        return collection.mean()
