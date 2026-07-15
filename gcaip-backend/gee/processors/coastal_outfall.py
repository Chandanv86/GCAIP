"""
gee/processors/coastal_outfall.py

Theme 9: Coastal Outfall Plume Processor.

Detects and characterizes marine discharge plumes (municipal wastewater, agricultural
runoff, or thermal cooling water) at coastal outfalls: extent, dispersion bearing, and
(where thermal signature is present) sea-surface-temperature anomaly.

Follows the same contract as the other theme processors: inherits BaseThemeProcessor,
returns a standardized ThemeResult, routes all GEE calls through gee_client.safe_call,
and degrades gracefully via ThemeResult.error_result on missing data.
"""

from __future__ import annotations

import math

import structlog
import ee

from gee import client as gee_client
from gee.client import GEEAssetNotFoundError, GEEQuotaError
from gee.processors.base import BaseThemeProcessor, ThemeResult
from services.adaptive_thresholds import sar_oil_sheen_mask

log = structlog.get_logger(__name__)

# cool blue (ambient) -> warm yellow/orange (plume core)
VIS_OUTFALL = {
    "min": 0,
    "max": 1,
    "palette": [
        "#08306b",
        "#2171b5",
        "#6baed6",
        "#fee391",
        "#fe9929",
        "#d94801",
    ],
}

# S2 SR reflectance bands in COPERNICUS/S2_SR_HARMONIZED are stored as
# integers scaled by 10,000 (reflectance 0-1 → stored as 0-10000).
# We normalise immediately after loading the composite (×0.0001) so all
# subsequent absolute-value comparisons use true 0-1 reflectance.
S2_SCALE_FACTOR = 0.0001
GLINT_B11_THRESHOLD = 0.02   # true reflectance (0-1 scale); equals raw value 200
CLOUD_COVER_MAX = 35
THERMAL_PLUME_DELTA_C = 1.5
SPM_A_COEFF = 355.85
SPM_C_COEFF = 0.1728


class CoastalOutfallProcessor(BaseThemeProcessor):
    """Detects coastal/marine outfall plumes and estimates dispersion bearing."""

    THEME_NAME = "coastal_outfall"

    def compute(self, aoi_geojson: dict, date_range: tuple[str, str]) -> ThemeResult:
        start, end = date_range
        try:
            aoi = self.get_aoi_geometry(aoi_geojson)
            # ── Applicability check: does this AOI contain any water? ─────────
            # Run this before fetching any imagery so we can surface a clear
            # "not applicable" result rather than a generic "no data" failure.
            # WorldCover class 80 = permanent water bodies (rivers, lakes, sea).
            wc_water_px = gee_client.get_stats(
                image=ee.ImageCollection("ESA/WorldCover/v200").first()
                    .select("Map").eq(80).rename("water"),
                aoi=aoi,
                scale=100,
                reducer=ee.Reducer.sum(),
                max_pixels=1e9,
            ).get("water") or 0
            if float(wc_water_px) < 10:
                # Fewer than 10 water pixels at 100m → no meaningful water body.
                # Coastal outfall analysis is geometrically inapplicable here.
                return ThemeResult.not_applicable_result(
                    self.THEME_NAME,
                    "No open-water pixels (WorldCover class 80) found within the AOI. "
                    "Coastal Outfall analysis requires at least a small water body "
                    "(river reach, estuary, or coastal zone). This AOI appears to be "
                    "purely terrestrial — retry will not help.",
                )
            outfall_point = self._resolve_outfall_anchor(aoi_geojson, aoi)
            return self._run_gee_analysis(aoi, outfall_point, start, end)
        except GEEAssetNotFoundError as exc:
            log.info("coastal_outfall.no_data", reason=str(exc))
            return ThemeResult.error_result(
                self.THEME_NAME,
                f"No usable marine imagery found for the requested window: {exc}",
                error_class="data_gap",
            )
        except GEEQuotaError as exc:
            log.warning("coastal_outfall.quota_exceeded", reason=str(exc))
            return ThemeResult.error_result(self.THEME_NAME, f"GEE quota exceeded: {exc}")
        except Exception as exc:  # noqa: BLE001
            log.exception("coastal_outfall.unexpected_error")
            return ThemeResult.error_result(self.THEME_NAME, f"Unexpected error: {exc}")

    # ------------------------------------------------------------------
    def _resolve_outfall_anchor(self, aoi_geojson: dict, aoi: "ee.Geometry") -> "ee.Geometry":
        """Use an explicit outfall_point property if the caller supplied one,
        otherwise fall back to the AOI centroid (documented assumption)."""
        props = aoi_geojson.get("properties", {}) if isinstance(aoi_geojson, dict) else {}
        outfall_coords = props.get("outfall_point")
        if outfall_coords and len(outfall_coords) == 2:
            return ee.Geometry.Point(outfall_coords)
        return aoi.centroid(maxError=10)

    # ------------------------------------------------------------------
    def _run_gee_analysis(
        self, aoi: "ee.Geometry", outfall_point: "ee.Geometry", start: str, end: str
    ) -> ThemeResult:
        water_mask = self._marine_water_mask(aoi)

        s2, s2_count, cloud_threshold_used = self._load_s2_collection(aoi, start, end)
        if s2_count == 0:
            # All S2 tiers exhausted: default/widen15/widen30/relax
            raise GEEAssetNotFoundError(
                "No cloud-free Sentinel-2 marine scenes across all fallback tiers"
            )

        # Normalise S2 SR bands from integer scale (0-10000) to true reflectance (0-1).
        # Must happen before ANY absolute-value comparison (glint threshold, SPM formula).
        # Normalised-difference indices (NDWI etc.) are scale-invariant, but are computed
        # later in this file from already-normalised bands via glint_free, so this is fine.
        current = s2.mean().multiply(S2_SCALE_FACTOR)

        # Glint suppression: mask any pixel with high SWIR1 reflectance (open water
        # is essentially opaque in SWIR, so signal there is glint/cloud, not water-leaving).
        # GLINT_B11_THRESHOLD = 0.02 is calibrated to true reflectance (0-1 scale).
        glint_free = current.updateMask(current.select("B11").lt(GLINT_B11_THRESHOLD))

        red = glint_free.select("B4")
        spm = red.expression(
            "(A * b) / (1 - (b / C))",
            {"A": SPM_A_COEFF, "C": SPM_C_COEFF, "b": red},
        ).rename("spm")
        cdom = glint_free.select("B2").divide(glint_free.select("B3")).rename("cdom")

        # Sobel edge / plume-front magnitude on combined SPM+CDOM signal
        combined = spm.unitScale(0, 50).add(cdom.unitScale(0.5, 2.0)).rename("plume_signal")
        sobel_kernel = ee.Kernel.sobel()
        gradient = combined.convolve(sobel_kernel).abs().rename("gradient")

        plume_signal_masked = combined.updateMask(water_mask)
        gradient_p90_raw = gee_client.get_stats(
            image=gradient.updateMask(water_mask),
            aoi=aoi,
            scale=10,
            reducer=ee.Reducer.percentile([90]),
            max_pixels=1e10,
        )
        # gradient_p90_raw can be empty if water_mask has no pixels in the AOI
        # (e.g., a purely inland or dry AOI where WorldCover class 80 is absent).
        # This is a genuine "no marine water here" signal — surface it clearly.
        if not gradient_p90_raw:
            raise GEEAssetNotFoundError(
                "No permanent-water pixels (WorldCover class 80) found within the AOI. "
                "CoastalOutfall processor requires at least some marine/coastal water coverage."
            )
        gradient_threshold = float(next(iter(gradient_p90_raw.values()), 0.5) or 0.5)
        mean_stats = gee_client.safe_call(
            plume_signal_masked.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=aoi,
                scale=10,
                maxPixels=1e10,
                bestEffort=True
            ).getInfo
        )
        mean_val = mean_stats.get("plume_signal") if mean_stats else None
        if mean_val is None:
            raise GEEAssetNotFoundError(
                "SWIR glint suppression or Sentinel-2 cloud masking filtered out all valid "
                "water pixels within the AOI, leaving no data to analyze. This is a common "
                "seasonal limitation under high cloud cover or severe sun glint."
            )
        plume_mask = plume_signal_masked.gt(float(mean_val)).And(water_mask)

        pixel_area_km2 = ee.Image.pixelArea().divide(1e6)
        area_stats = gee_client.get_stats(
            image=pixel_area_km2.updateMask(plume_mask).rename("impact_area_km2"),
            aoi=aoi,
            scale=10,
            reducer=ee.Reducer.sum(),
            max_pixels=1e10,
        )
        impact_area_km2 = float(area_stats.get("impact_area_km2") or 0.0)

        index_stats = gee_client.get_stats(
            image=ee.Image.cat([spm.rename("spm_mean"), cdom.rename("cdom_mean")]).updateMask(water_mask),
            aoi=aoi,
            scale=10,
            reducer=ee.Reducer.mean(),
            max_pixels=1e10,
        )
        # If the water_mask produces no pixels (or SPM formula returns no-data),
        # index_stats values will be None — float(None) raises TypeError. Raise
        # explicitly with a clear reason rather than crashing with a bare type error.
        _spm_raw = index_stats.get("spm_mean")
        _cdom_raw = index_stats.get("cdom_mean")
        if _spm_raw is None or _cdom_raw is None:
            raise GEEAssetNotFoundError(
                f"SPM/CDOM zonal statistics returned no data for the AOI water pixels. "
                f"This typically means the SWIR glint mask or WorldCover water mask "
                f"filtered out all valid pixels (spm_mean={_spm_raw}, cdom_mean={_cdom_raw})."
            )
        spm_mean = float(_spm_raw)
        cdom_mean = float(_cdom_raw)

        thermal_result = self._thermal_plume_analysis(aoi, start, end, water_mask)

        # --- SAR oil-sheen detection (independent of SPM/CDOM, surfaces as own stat) ---
        # Pattern reused from erosion.py: ERA5-Land u/v -> sqrt(u^2 + v^2) m/s.
        # S1 collection reuses the same IW/VV filter pattern as pipeline_corridor.py.
        oil_sheen_km2 = 0.0
        oil_sheen_diagnostics: dict = {"sar_oil_sheen_checked": False}
        try:
            era5_wind = (
                ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
                .filterBounds(aoi)
                .filterDate(start, end)
                .select(["u_component_of_wind_10m", "v_component_of_wind_10m"])
                .mean()
            )
            wind_stats = gee_client.get_stats(
                image=era5_wind, aoi=aoi, scale=11000,
                reducer=ee.Reducer.mean(), max_pixels=1e8,
            )
            u = float(wind_stats.get("u_component_of_wind_10m", 0) or 0)
            v = float(wind_stats.get("v_component_of_wind_10m", 0) or 0)
            wind_speed_ms: float | None = math.sqrt(u ** 2 + v ** 2)
        except Exception as era5_exc:
            log.warning("coastal_outfall.era5_wind_failed", error=str(era5_exc))
            wind_speed_ms = None

        try:
            s1_for_sheen = (
                ee.ImageCollection("COPERNICUS/S1_GRD")
                .filterBounds(aoi)
                .filterDate(start, end)
                .filter(ee.Filter.eq("instrumentMode", "IW"))
                .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
            )
            oil_mask, oil_sheen_diagnostics = sar_oil_sheen_mask(s1_for_sheen, aoi, wind_speed_ms)
            if oil_mask is not None:
                oil_area_stats = gee_client.get_stats(
                    image=ee.Image.pixelArea().updateMask(oil_mask).divide(1e6)
                        .rename("oil_sheen_km2"),
                    aoi=aoi, scale=10, reducer=ee.Reducer.sum(), max_pixels=1e10,
                )
                oil_sheen_km2 = round(float(oil_area_stats.get("oil_sheen_km2") or 0), 4)
        except Exception as sar_exc:
            log.warning("coastal_outfall.sar_oil_sheen_error", error=str(sar_exc))
            oil_sheen_diagnostics["skip_reason"] = str(sar_exc)

        # --- Dispersion bearing: plume centroid vs. outfall anchor ---
        bearing_deg = self._dispersion_bearing(plume_mask, aoi, outfall_point)

        # aggregate_max returns a lazy ee.ComputedObject in real GEE — must call
        # .getInfo() to resolve to a Python number. In mocks it's already a scalar.
        _ts_obj = gee_client.safe_call(s2.aggregate_max, "system:time_start")
        if _ts_obj is None:
            latest_millis = None
        elif hasattr(_ts_obj, "getInfo"):
            latest_millis = gee_client.safe_call(_ts_obj.getInfo)
        else:
            latest_millis = _ts_obj  # already a Python scalar
        data_age_hours = self.data_age_from_millis(latest_millis)

        confidence = min(1.0, 0.5 + 0.08 * s2_count)
        # P6 fix: previous floor was 0.2, which meant fallback-tier results (1 scene)
        # reach confidence=0.48 but fail per-rule thresholds (0.6) in AlertEngine,
        # silently suppressing real detections. Floor raised to 0.35 so genuine signals
        # above the 0.4 global alert threshold can still trigger alerts.
        confidence = max(0.35, confidence - 0.1)  # tidal-completeness penalty (no tide API wired yet)

        # water surface area for normalization
        water_area_stats = gee_client.get_stats(
            image=pixel_area_km2.updateMask(water_mask).rename("water_area_km2"),
            aoi=aoi, scale=10, reducer=ee.Reducer.sum(), max_pixels=1e10,
        )
        water_area_km2 = max(float(water_area_stats.get("water_area_km2") or 0.01), 0.01)
        anomaly_score = min(100.0, (impact_area_km2 / water_area_km2) * 250.0)
        if thermal_result["thermal_plume_flag"]:
            anomaly_score = min(100.0, anomaly_score + 20.0)

        tile_url, tile_expires_at = gee_client.get_tile_url(
            combined.updateMask(water_mask).clip(aoi).visualize(**VIS_OUTFALL), {}
        )

        return ThemeResult(
            theme=self.THEME_NAME,
            tile_url=tile_url,
            tile_url_expires_at=tile_expires_at,
            vis_params=VIS_OUTFALL,
            metric_value=round(impact_area_km2, 4),
            metric_unit="km2",
            metric_label="Coastal Outfall Impact Area",
            stats={
                "outfall_impact_area_km2": round(impact_area_km2, 4),
                "dispersion_bearing_deg": bearing_deg,
                "spm_mean": round(spm_mean, 3),
                "cdom_index_mean": round(cdom_mean, 3),
                "water_area_km2": round(water_area_km2, 4),
                "tidal_stage": "unknown",
                "cloud_threshold_used": cloud_threshold_used,
                # SAR oil-sheen stats — independent of SPM/CDOM pipeline
                "oil_sheen_km2": oil_sheen_km2,
                "oil_sheen_diagnostics": oil_sheen_diagnostics,
                **thermal_result,
                "caveats": [
                    "SPM/CDOM are relative proxies using generic global calibration "
                    "coefficients; absolute mg/L values require local in-situ calibration.",
                    "Tidal stage integration is not yet wired; a fixed confidence "
                    "penalty is applied until a tide-gauge/model API is available.",
                    "Dispersion bearing assumes AOI centroid as outfall anchor unless "
                    "an explicit outfall_point property is supplied on the AOI.",
                    "SAR oil-sheen detection requires wind speed >= 3 m/s to distinguish "
                    "oil films from naturally calm water; see oil_sheen_diagnostics.wind_gate_passed.",
                ],
            },
            anomaly_score=round(anomaly_score, 2),
            confidence=round(confidence, 2),
            data_age_hours=round(data_age_hours, 2) if data_age_hours is not None else None,
            data_source="sentinel2+landsat_thermal",
        )

    # ------------------------------------------------------------------
    def _load_s2_collection(
        self, aoi: "ee.Geometry", start: str, end: str
    ) -> tuple["ee.ImageCollection", int, int]:
        """Load S2 collection with progressive fallback: default -> widen 15d -> widen 30d -> relax cloud (60%)"""
        from datetime import date, timedelta
        start_dt = date.fromisoformat(start)

        def _s2_col(s: str, e: str, cloud_pct: int):
            return (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(aoi)
                .filterDate(s, e)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_pct))
                .map(self.apply_s2_cloud_mask)
            )

        # Tier 1: Default
        col = _s2_col(start, end, CLOUD_COVER_MAX)
        cnt = gee_client.safe_call(col.size().getInfo)
        if cnt > 0:
            return col, cnt, CLOUD_COVER_MAX

        # Tier 2: Widen 15d
        w15_start = (start_dt - timedelta(days=15)).isoformat()
        log.info("coastal_outfall.fallback_s2_widen_15d", start=w15_start, end=end)
        col = _s2_col(w15_start, end, CLOUD_COVER_MAX)
        cnt = gee_client.safe_call(col.size().getInfo)
        if cnt > 0:
            return col, cnt, CLOUD_COVER_MAX

        # Tier 3: Widen 30d
        w30_start = (start_dt - timedelta(days=30)).isoformat()
        log.info("coastal_outfall.fallback_s2_widen_30d", start=w30_start, end=end)
        col = _s2_col(w30_start, end, CLOUD_COVER_MAX)
        cnt = gee_client.safe_call(col.size().getInfo)
        if cnt > 0:
            return col, cnt, CLOUD_COVER_MAX

        # Tier 4: Relax cloud
        log.info("coastal_outfall.fallback_s2_relaxed_cloud", threshold=60)
        col = _s2_col(start, end, 60)
        cnt = gee_client.safe_call(col.size().getInfo)
        return col, cnt, 60

    # ------------------------------------------------------------------
    def _marine_water_mask(self, aoi: "ee.Geometry") -> "ee.Image":
        worldcover = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
        static_water = worldcover.eq(80)
        return static_water

    # ------------------------------------------------------------------
    def _thermal_plume_analysis(
        self, aoi: "ee.Geometry", start: str, end: str, water_mask: "ee.Image"
    ) -> dict:
        landsat = (
            ee.ImageCollection("LANDSAT/LC09/C02/T1_L2")
            .merge(ee.ImageCollection("LANDSAT/LC08/C02/T1_L2"))
            .filterBounds(aoi)
            .filterDate(start, end)
            .filter(ee.Filter.lt("CLOUD_COVER", CLOUD_COVER_MAX))
        )
        count = gee_client.safe_call(landsat.size().getInfo)
        if count == 0:
            return {"delta_sst_c": None, "thermal_plume_flag": False, "thermal_source": "unavailable"}

        lst_kelvin = landsat.mean().select("ST_B10").multiply(0.00341802).add(149.0)
        lst_celsius = lst_kelvin.subtract(273.15).rename("lst_c")

        ambient_ring = aoi.buffer(3000).difference(aoi.buffer(1000))
        ambient_stats = gee_client.get_stats(
            image=lst_celsius.updateMask(water_mask),
            aoi=ambient_ring,
            scale=30,
            reducer=ee.Reducer.mean(),
            max_pixels=1e10,
        )
        plume_stats = gee_client.get_stats(
            image=lst_celsius.updateMask(water_mask),
            aoi=aoi,
            scale=30,
            reducer=ee.Reducer.mean(),
            max_pixels=1e10,
        )
        ambient_c = ambient_stats.get("lst_c")
        plume_c = plume_stats.get("lst_c")
        if ambient_c is None or plume_c is None:
            return {"delta_sst_c": None, "thermal_plume_flag": False, "thermal_source": "landsat_incomplete"}

        delta = float(plume_c) - float(ambient_c)
        return {
            "delta_sst_c": round(delta, 2),
            "thermal_plume_flag": delta > THERMAL_PLUME_DELTA_C,
            "thermal_source": "landsat_st_b10",
        }

    # ------------------------------------------------------------------
    def _dispersion_bearing(
        self, plume_mask: "ee.Image", aoi: "ee.Geometry", outfall_point: "ee.Geometry"
    ) -> float | None:
        lon_lat = ee.Image.pixelLonLat().updateMask(plume_mask)
        centroid_stats = gee_client.get_stats(
            image=lon_lat, aoi=aoi, scale=10, reducer=ee.Reducer.mean(), max_pixels=1e10
        )
        plume_lon = centroid_stats.get("longitude")
        plume_lat = centroid_stats.get("latitude")
        if plume_lon is None or plume_lat is None:
            return None

        anchor_coords = gee_client.safe_call(outfall_point.coordinates().getInfo)
        anchor_lon, anchor_lat = anchor_coords[0], anchor_coords[1]

        d_lon = math.radians(float(plume_lon) - anchor_lon)
        lat1 = math.radians(anchor_lat)
        lat2 = math.radians(float(plume_lat))
        x = math.sin(d_lon) * math.cos(lat2)
        y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
        bearing = (math.degrees(math.atan2(x, y)) + 360) % 360
        return round(bearing, 1)
