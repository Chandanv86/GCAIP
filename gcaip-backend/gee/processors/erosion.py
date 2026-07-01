"""
GCAIP Theme 5 — Coastal Erosion Rate Processor

Algorithm: Sentinel-1 + Sentinel-2 NDWI multi-temporal shoreline extraction.
Computes End Point Rate (EPR) = Net Shoreline Movement / years elapsed.

EPR < 0 = erosion (retreat); EPR > 0 = accretion.
Infrastructure trajectory is computed in services/trajectory.py after enrichment.
"""
import structlog
from datetime import date, timedelta

import ee

from gee import client as gee_client
from gee.processors.base import BaseThemeProcessor, ThemeResult

log = structlog.get_logger(__name__)

VIS_EROSION = {
    "min": -5,
    "max": 5,
    "palette": [
        "#d73027",  # strong erosion (< -3 m/yr)
        "#fc8d59",
        "#fee090",  # mild erosion
        "#e0f3f8",  # stable
        "#91bfdb",  # mild accretion
        "#4575b4",  # strong accretion
    ],
}


class ErosionProcessor(BaseThemeProcessor):
    THEME_NAME = "erosion"

    def compute(
        self, aoi_geojson: dict, date_range: tuple[str, str]
    ) -> ThemeResult:
        aoi = self.get_aoi_geometry(aoi_geojson)
        start_date, end_date = date_range
        try:
            return gee_client.safe_call(
                self._run_gee_analysis, aoi, start_date, end_date
            )
        except Exception as exc:
            log.error("erosion.compute_error", error=str(exc))
            return ThemeResult.error_result(self.THEME_NAME, str(exc))

    def _run_gee_analysis(
        self, aoi: "ee.Geometry", start_date: str, end_date: str
    ) -> ThemeResult:
        end = date.fromisoformat(end_date)

        # ── Current shoreline via Sentinel-1 SAR ─────────────────────────────
        s1_current = (
            ee.ImageCollection("COPERNICUS/S1_GRD")
            .filterBounds(aoi)
            .filterDate(start_date, end_date)
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .select("VV")
        )
        s1_count = s1_current.size().getInfo()
        if s1_count == 0:
            raise gee_client.GEEAssetNotFoundError("No S1 data for erosion analysis")

        # SAR water mask: VV < -15 dB in dB scale
        current_vv_db = s1_current.mean().log10().multiply(10)
        current_water = current_vv_db.lt(-15.0).rename("water")

        # ── Reference shoreline: 24 months prior ─────────────────────────────
        ref_end = (end - timedelta(days=720)).isoformat()
        ref_start = (end - timedelta(days=750)).isoformat()
        s1_reference = (
            ee.ImageCollection("COPERNICUS/S1_GRD")
            .filterBounds(aoi)
            .filterDate(ref_start, ref_end)
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .select("VV")
        )
        ref_count = s1_reference.size().getInfo()
        if ref_count == 0:
            # Try Sentinel-2 NDWI as fallback
            return self._ndwi_fallback(aoi, start_date, end_date)

        ref_vv_db = s1_reference.mean().log10().multiply(10)
        reference_water = ref_vv_db.lt(-15.0).rename("water_ref")

        # ── Shoreline change detection ────────────────────────────────────────
        # Erosion: was land (ref=0), now water (current=1)
        erosion = reference_water.Not().And(current_water).rename("eroded")
        # Accretion: was water (ref=1), now land (current=0)
        accretion = reference_water.And(current_water.Not()).rename("accreted")

        pixel_area_m2 = ee.Image.pixelArea()

        erosion_stats = gee_client.get_stats(
            image=erosion.multiply(pixel_area_m2).rename("area"),
            aoi=aoi, scale=20, reducer=ee.Reducer.sum(),
        )
        accretion_stats = gee_client.get_stats(
            image=accretion.multiply(pixel_area_m2).rename("area"),
            aoi=aoi, scale=20, reducer=ee.Reducer.sum(),
        )
        total_stats = gee_client.get_stats(
            image=ee.Image.pixelArea().rename("area"),
            aoi=aoi, scale=100, reducer=ee.Reducer.sum(),
        )

        eroded_m2 = float(erosion_stats.get("area", 0) or 0)
        accreted_m2 = float(accretion_stats.get("area", 0) or 0)
        total_m2 = float(total_stats.get("area", 1) or 1)

        # Estimate coast length (sqrt of area as rough proxy × 2)
        import math
        coast_length_m = math.sqrt(total_m2) * 2
        years_elapsed = 2.0  # 24-month window

        # EPR in m/yr — negative = erosion
        nsm_erosion_m = -(eroded_m2 / coast_length_m)  # negative = retreat
        nsm_accretion_m = accreted_m2 / coast_length_m

        # Net EPR
        mean_epr = (nsm_accretion_m + nsm_erosion_m) / years_elapsed
        max_erosion_m_yr = nsm_erosion_m / years_elapsed

        # Percentage classification
        aoi_coast_m2 = total_m2
        eroding_pct = (eroded_m2 / aoi_coast_m2) * 100 if aoi_coast_m2 > 0 else 0
        accreting_pct = (accreted_m2 / aoi_coast_m2) * 100 if aoi_coast_m2 > 0 else 0
        stable_pct = max(0.0, 100.0 - eroding_pct - accreting_pct)

        # ── ERA5 wind speed as wave proxy ─────────────────────────────────────
        era5_wind = (
            ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
            .filterBounds(aoi)
            .filterDate(start_date, end_date)
            .select(["u_component_of_wind_10m", "v_component_of_wind_10m"])
            .sort("system:time_start", False)
            .first()
        )
        wind_stats = gee_client.get_stats(
            image=era5_wind, aoi=aoi, scale=11000,
            reducer=ee.Reducer.mean(),
        )
        u = float(wind_stats.get("u_component_of_wind_10m", 0) or 0)
        v = float(wind_stats.get("v_component_of_wind_10m", 0) or 0)
        wind_speed = math.sqrt(u ** 2 + v ** 2)  # m/s
        storm_wave_risk = (
            "HIGH" if wind_speed > 15 else
            "MEDIUM" if wind_speed > 10 else "LOW"
        )

        # ── Tile URL ──────────────────────────────────────────────────────────
        # EPR map: erosion=negative, accretion=positive
        epr_img = (
            erosion.multiply(-1)
            .add(accretion)
            .rename("EPR")
            .unmask(0)
            .toFloat()
        )
        tile_url, expires_at = gee_client.get_tile_url(epr_img, VIS_EROSION)

        confidence = min(1.0, 0.5 + (s1_count + ref_count) * 0.05)
        anomaly_score = min(100.0, abs(mean_epr) / 5.0 * 100.0)  # 5 m/yr = score 100

        metric_label = (
            f"Shoreline retreating at {abs(mean_epr):.1f} m/yr"
            if mean_epr < 0
            else f"Shoreline accreting at {mean_epr:.1f} m/yr"
        )

        return ThemeResult(
            theme=self.THEME_NAME,
            tile_url=tile_url,
            tile_url_expires_at=expires_at,
            vis_params=VIS_EROSION,
            metric_value=mean_epr,
            metric_unit="m/yr",
            metric_label=metric_label,
            stats={
                "mean_epr_m_yr": round(mean_epr, 2),
                "max_erosion_m_yr": round(max_erosion_m_yr, 2),
                "eroding_pct": round(eroding_pct, 1),
                "accreting_pct": round(accreting_pct, 1),
                "stable_pct": round(stable_pct, 1),
                "eroded_area_m2": round(eroded_m2, 0),
                "accreted_area_m2": round(accreted_m2, 0),
                "storm_wave_risk": storm_wave_risk,
                "wind_speed_ms": round(wind_speed, 1),
                "reference_period": f"{ref_start} to {ref_end}",
                "years_elapsed": years_elapsed,
            },
            anomaly_score=round(anomaly_score, 1),
            confidence=round(confidence, 2),
            data_age_hours=self.data_age_from_millis(
                s1_current.sort("system:time_start", False)
                .first().get("system:time_start").getInfo()
            ),
            data_source=f"Sentinel-1 GRD (2-year change), {end_date}",
            error=None,
        )

    def _ndwi_fallback(
        self, aoi: "ee.Geometry", start_date: str, end_date: str
    ) -> ThemeResult:
        """Fall back to Sentinel-2 NDWI when SAR reference unavailable."""
        s2 = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(aoi)
            .filterDate(start_date, end_date)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
            .map(self.apply_s2_cloud_mask)
        )
        if s2.size().getInfo() == 0:
            return ThemeResult.error_result(
                self.THEME_NAME, "No SAR or optical data for shoreline analysis."
            )
        green = s2.median().select("B3")
        nir = s2.median().select("B8")
        ndwi = green.subtract(nir).divide(green.add(nir)).rename("NDWI")
        water = ndwi.gt(0.0).rename("water")
        tile_url, expires_at = gee_client.get_tile_url(
            water, {"min": 0, "max": 1, "palette": ["white", "#1E88E5"]}
        )
        return ThemeResult(
            theme=self.THEME_NAME,
            tile_url=tile_url,
            tile_url_expires_at=expires_at,
            vis_params={"min": 0, "max": 1, "palette": ["white", "#1E88E5"]},
            metric_value=0.0,
            metric_unit="m/yr",
            metric_label="Shoreline mapped (rate unavailable — insufficient SAR history)",
            stats={"ndwi_fallback": True},
            anomaly_score=0.0,
            confidence=0.35,
            data_age_hours=48.0,
            data_source=f"Sentinel-2 NDWI fallback, {end_date}",
            error=None,
        )
