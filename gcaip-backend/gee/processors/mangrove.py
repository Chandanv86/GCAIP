"""
GCAIP Theme 4 — Mangrove Restoration Processor

Algorithm: GMW v3 baseline + Sentinel-2 MVI (Mangrove Vegetation Index)
MVI = SWIR1 / NIR (Band 11 / Band 8) — threshold > 1.0 = mangrove canopy

NOTE: GMW v3 asset path may change. Current confirmed path:
  projects/mangrovecapital/assets/GMW/v3/GMW_v3_2020_vec
  Verify in GEE catalog before production deployment.
  Fallback: use Sentinel-2 MVI alone.
"""
import structlog
from datetime import date, timedelta

import ee

from gee import client as gee_client
from gee.processors.base import BaseThemeProcessor, ThemeResult

log = structlog.get_logger(__name__)

# CARBON: conservative mangrove carbon density = 200 tCO2e/ha
CARBON_DENSITY_TCO2_HA = 200.0

VIS_MANGROVE = {
    "min": 0,
    "max": 2,
    "palette": [
        "#FFFFFF",  # 0 = not mangrove
        "#1a7a4a",  # 1 = stable mangrove
        "#ff6600",  # 2 = gain (new mangrove vs baseline)
    ],
}

# GMW v3 2020 asset — VERIFY this path in GEE catalog
GMW_ASSET = "projects/mangrovecapital/assets/GMW/v3/GMW_v3_2020_vec"


class MangroveProcessor(BaseThemeProcessor):
    THEME_NAME = "mangrove"

    def compute(
        self, aoi_geojson: dict, date_range: tuple[str, str]
    ) -> ThemeResult:
        aoi = self.get_aoi_geometry(aoi_geojson)
        _, end_date = date_range
        try:
            return gee_client.safe_call(
                self._run_gee_analysis, aoi, end_date
            )
        except Exception as exc:
            log.error("mangrove.compute_error", error=str(exc))
            return ThemeResult.error_result(self.THEME_NAME, str(exc))

    def _run_gee_analysis(
        self, aoi: "ee.Geometry", end_date: str
    ) -> ThemeResult:
        end = date.fromisoformat(end_date)
        start_date = (end - timedelta(days=60)).isoformat()  # 60-day S2 window

        # ── Sentinel-2 cloud-free composite ──────────────────────────────────
        s2 = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(aoi)
            .filterDate(start_date, end_date)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
            .map(self.apply_s2_cloud_mask)
        )

        scene_count = s2.size().getInfo()
        if scene_count == 0:
            # Relax cloud filter
            s2 = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(aoi)
                .filterDate(start_date, end_date)
                .map(self.apply_s2_cloud_mask)
            )
            scene_count = s2.size().getInfo()

        if scene_count == 0:
            raise gee_client.GEEAssetNotFoundError("No Sentinel-2 scenes available")

        s2_composite = s2.median()
        confidence = min(1.0, 0.5 + scene_count * 0.08)

        # ── MVI: SWIR1 / NIR (Band 11 / Band 8) ─────────────────────────────
        # S2 bands: B4=Red, B8=NIR, B11=SWIR1, B12=SWIR2
        # MVI threshold: MVI > 1.0 identifies mangrove canopy structure
        nir = s2_composite.select("B8")
        swir1 = s2_composite.select("B11")
        mvi = swir1.divide(nir).rename("MVI")
        current_mangrove = mvi.gt(1.0).selfMask().rename("mangrove")

        # ── NDVI for canopy health ────────────────────────────────────────────
        red = s2_composite.select("B4")
        ndvi = nir.subtract(red).divide(nir.add(red)).rename("NDVI")
        # Mean NDVI within detected mangrove pixels
        ndvi_stats = gee_client.get_stats(
            image=ndvi.updateMask(current_mangrove),
            aoi=aoi, scale=20,
            reducer=ee.Reducer.mean(),
        )
        ndvi_mean = float(ndvi_stats.get("NDVI", 0) or 0)

        # ── Area statistics ───────────────────────────────────────────────────
        pixel_area_ha = ee.Image.pixelArea().divide(10000)  # m² → ha
        current_area_stats = gee_client.get_stats(
            image=current_mangrove.multiply(pixel_area_ha).rename("area"),
            aoi=aoi, scale=20,
            reducer=ee.Reducer.sum(),
        )
        total_ha = float(current_area_stats.get("area", 0) or 0)

        # ── GMW v3 baseline comparison ────────────────────────────────────────
        try:
            gmw_baseline = (
                ee.FeatureCollection(GMW_ASSET)
                .filterBounds(aoi)
            )
            # Rasterize GMW vector to 20m
            gmw_raster = (
                gmw_baseline.map(lambda f: f.set("gmw", 1))
                .reduceToImage(properties=["gmw"], reducer=ee.Reducer.first())
                .unmask(0)
                .rename("gmw")
            )
            # Gain: current mangrove but not in GMW baseline
            gain = current_mangrove.And(gmw_raster.Not())
            gain_stats = gee_client.get_stats(
                image=gain.multiply(pixel_area_ha).rename("area"),
                aoi=aoi, scale=20, reducer=ee.Reducer.sum(),
            )
            gain_ha = float(gain_stats.get("area", 0) or 0)

            # Loss: GMW baseline but not current mangrove
            loss = gmw_raster.And(current_mangrove.Not())
            loss_stats = gee_client.get_stats(
                image=loss.multiply(pixel_area_ha).rename("area"),
                aoi=aoi, scale=20, reducer=ee.Reducer.sum(),
            )
            loss_ha = float(loss_stats.get("area", 0) or 0)

            has_gmw = True
        except Exception as gmw_exc:
            log.warning("mangrove.gmw_unavailable", error=str(gmw_exc))
            gain_ha = 0.0
            loss_ha = 0.0
            has_gmw = False

        net_change_ha = gain_ha - loss_ha

        # ── Carbon estimates (rough) ──────────────────────────────────────────
        carbon_tco2 = total_ha * CARBON_DENSITY_TCO2_HA
        annual_seq_tco2 = net_change_ha * CARBON_DENSITY_TCO2_HA

        # ── Canopy health score ───────────────────────────────────────────────
        # NDVI 0.7+ = excellent, 0.4 = stressed, < 0.3 = degraded
        health_score = min(100.0, max(0.0, (ndvi_mean - 0.2) / 0.6 * 100.0))

        # ── Tile URL ──────────────────────────────────────────────────────────
        # Show: 0=background, 1=stable, 2=gain
        vis_img = current_mangrove.unmask(0)
        if has_gmw:
            vis_img = vis_img.where(gain.unmask(0), 2)
        tile_url, expires_at = gee_client.get_tile_url(vis_img, VIS_MANGROVE)

        anomaly_score = min(100.0, abs(net_change_ha) / max(total_ha, 1) * 200)

        metric_label = (
            f"{total_ha:,.0f} ha mangrove"
            + (f" (+{net_change_ha:+.0f} ha vs GMW baseline)" if has_gmw else "")
        )

        return ThemeResult(
            theme=self.THEME_NAME,
            tile_url=tile_url,
            tile_url_expires_at=expires_at,
            vis_params=VIS_MANGROVE,
            metric_value=total_ha,
            metric_unit="ha",
            metric_label=metric_label,
            stats={
                "total_ha": round(total_ha, 1),
                "gain_ha": round(gain_ha, 1) if has_gmw else None,
                "loss_ha": round(loss_ha, 1) if has_gmw else None,
                "net_change_ha": round(net_change_ha, 1),
                "canopy_ndvi_mean": round(ndvi_mean, 3),
                "health_score": round(health_score, 1),
                "carbon_estimate_tco2": round(carbon_tco2, 0),
                "annual_sequestration_tco2": round(annual_seq_tco2, 0),
                "gmw_baseline_used": has_gmw,
                "s2_scene_count": scene_count,
            },
            anomaly_score=round(anomaly_score, 1),
            confidence=round(confidence, 2),
            data_age_hours=48.0,  # S2 composites typically < 2 days
            data_source=f"Sentinel-2 SR + GMW v3 baseline, composite to {end_date}",
            error=None,
        )
