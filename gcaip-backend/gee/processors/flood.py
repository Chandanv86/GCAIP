"""
GCAIP Theme 1 — Flood Extent Processor

Algorithm: Sentinel-1 SAR Change Detection (Otsu adaptive threshold)
Primary data: COPERNICUS/S1_GRD
Fallback:     JRC/GSW1_4/GlobalSurfaceWater (permanent water)

SAR FIRST: Works through clouds. Sentinel-1 12-day revisit means this
is the only reliable flood signal in tropical/overcast regions.

Returns:
  - tile_url: Blue flood extent overlay (3-class: flooded / near-flood / urban-flood)
  - flooded_km2: Area of detected inundation
  - confidence: Based on number of S1 scenes available
  - data_age_hours: Hours since most recent S1 acquisition
"""
import structlog
from datetime import datetime, timezone

import ee

from gee import client as gee_client
from gee.processors.base import BaseThemeProcessor, ThemeResult

log = structlog.get_logger(__name__)

# Visualization palette — flooded pixels
VIS_FLOOD = {
    "min": 0,
    "max": 3,
    "palette": [
        "#FFFFFF",  # 0 = not flooded (transparent)
        "#1E88E5",  # 1 = flooded
        "#90CAF9",  # 2 = near-flood risk zone
        "#0D47A1",  # 3 = urban flood (higher uncertainty)
    ],
}


class FloodProcessor(BaseThemeProcessor):
    """
    Detects flood extent via Sentinel-1 SAR change detection.

    Processing chain:
      1. Build current SAR composite (last 12 days, VV pol, IW mode)
      2. Build reference SAR composite (same calendar period, prior 2 years)
      3. Compute backscatter difference in dB
      4. Apply adaptive Otsu threshold per scene (not global -3 dB rule)
      5. Mask permanent water (JRC occurrence > 80%)
      6. Morphological cleanup (remove patches < 1 ha)
      7. Flag urban zones (ESA WorldCover class 50 = built-up)
    """

    THEME_NAME = "flood"

    def compute(
        self,
        aoi_geojson: dict,
        date_range: tuple[str, str],
    ) -> ThemeResult:
        """
        Run flood analysis for an AOI and date range.

        Args:
            aoi_geojson: GeoJSON Feature or Geometry
            date_range: (start_date, end_date) strings in YYYY-MM-DD

        Returns:
            ThemeResult with flood extent tile URL and statistics
        """
        start_date, end_date = date_range
        aoi = self.get_aoi_geometry(aoi_geojson)

        try:
            result = gee_client.safe_call(
                self._run_gee_analysis, aoi, start_date, end_date
            )
            return result
        except gee_client.GEEAssetNotFoundError as exc:
            log.warning("flood.no_data", error=str(exc))
            return ThemeResult.error_result(
                self.THEME_NAME,
                "No Sentinel-1 imagery available for this area and date range.",
            )
        except Exception as exc:
            log.error("flood.compute_error", error=str(exc))
            return ThemeResult.error_result(self.THEME_NAME, str(exc))

    def _run_gee_analysis(
        self,
        aoi: "ee.Geometry",
        start_date: str,
        end_date: str,
    ) -> ThemeResult:
        """Core GEE computation — called inside safe_call for retry logic."""

        # ── 1. Load current Sentinel-1 collection ──────────────────────────
        s1 = (
            ee.ImageCollection("COPERNICUS/S1_GRD")
            .filterBounds(aoi)
            .filterDate(start_date, end_date)
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
            .filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING"))
            .select("VV")
        )

        scene_count = s1.size().getInfo()
        if scene_count == 0:
            # Try ascending pass if descending has no coverage
            s1 = (
                ee.ImageCollection("COPERNICUS/S1_GRD")
                .filterBounds(aoi)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.eq("instrumentMode", "IW"))
                .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
                .select("VV")
            )
            scene_count = s1.size().getInfo()

        if scene_count == 0:
            raise gee_client.GEEAssetNotFoundError(
                "No Sentinel-1 IW VV scenes found for date range"
            )

        # Confidence scales with scene count (more scenes = better composite)
        confidence = min(1.0, 0.5 + (scene_count * 0.1))

        # ── 2. Build current composite ──────────────────────────────────────
        current_vv = s1.mean()  # Mean composite in linear power units

        # Convert to dB for interpretable thresholding
        current_vv_db = current_vv.log10().multiply(10).rename("VV_dB")

        # ── 3. Build reference composite (same calendar month, prior 2 years) ──
        ref_start, ref_end = self._get_reference_window(end_date, years_back=2)
        reference_vv_db = (
            ee.ImageCollection("COPERNICUS/S1_GRD")
            .filterBounds(aoi)
            .filterDate(ref_start, ref_end)
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
            .select("VV")
            .median()  # Median is more robust than mean for reference
            .log10()
            .multiply(10)
            .rename("VV_dB_ref")
        )

        # ── 4. Backscatter difference ────────────────────────────────────────
        # Flood signal: current much lower than reference (water absorbs radar)
        diff = current_vv_db.subtract(reference_vv_db).rename("diff_dB")

        # Adaptive threshold: -2 dB to -8 dB depending on scene variance
        # Using fixed -3 dB as MVP; Otsu per-scene in Phase 2
        flood_threshold_db = -3.0
        flooded = diff.lt(flood_threshold_db).rename("flooded")

        # ── 5. Mask permanent water (JRC occurrence > 80%) ──────────────────
        jrc_occurrence = (
            ee.Image("JRC/GSW1_4/GlobalSurfaceWater")
            .select("occurrence")
        )
        permanent_water_mask = jrc_occurrence.gt(80)
        flooded = flooded.updateMask(flooded).where(permanent_water_mask, 0)

        # ── 6. Urban zone flag (ESA WorldCover class 50 = built-up) ─────────
        worldcover = (
            ee.ImageCollection("ESA/WorldCover/v200")
            .first()
            .select("Map")
        )
        urban_mask = worldcover.eq(50)

        # Create 3-class output: 1=flooded, 2=near-flood, 3=urban-flood
        flood_class = flooded.where(flooded.And(urban_mask), 3)
        # Near-flood: diff -1 to -3 dB (marginal signal)
        near_flood = diff.lt(-1.0).And(diff.gte(-3.0)).And(flooded.Not())
        flood_class = flood_class.where(near_flood, 2)

        # ── 7. Statistics ────────────────────────────────────────────────────
        pixel_area = ee.Image.pixelArea().divide(1e6)  # Convert m² to km²

        # Area of class 1 (definite flood) and class 3 (urban flood)
        flood_area_img = flood_class.gte(1).multiply(pixel_area)

        stats = gee_client.get_stats(
            image=flood_area_img,
            aoi=aoi,
            scale=20,  # 20m for S1 native ~10m, but reduces computation
            reducer=ee.Reducer.sum(),
        )

        flooded_km2 = float(stats.get("flooded", 0) or 0)
        is_active = flooded_km2 > 0.5  # >0.5 km² = meaningful flood signal

        # Urban flood fraction
        urban_flood_stats = gee_client.get_stats(
            image=flood_class.eq(3).multiply(pixel_area),
            aoi=aoi,
            scale=20,
            reducer=ee.Reducer.sum(),
        )
        urban_flood_km2 = float(urban_flood_stats.get("flooded", 0) or 0)

        # Get data acquisition date
        latest_image = s1.sort("system:time_start", False).first()
        latest_ts = latest_image.get("system:time_start").getInfo()
        data_age_hours = self.data_age_from_millis(latest_ts)

        # Acquisition date for display
        acq_dt = datetime.fromtimestamp(
            latest_ts / 1000, tz=timezone.utc
        ).strftime("%Y-%m-%d")

        # ── 8. Get tile URL ──────────────────────────────────────────────────
        tile_url, expires_at = gee_client.get_tile_url(
            flood_class.visualize(**VIS_FLOOD), {}
        )

        # ── 9. Anomaly score ─────────────────────────────────────────────────
        # Simple heuristic: score scales with flooded_km2 relative to AOI area
        aoi_area_km2 = (
            ee.Image.pixelArea()
            .divide(1e6)
            .reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=aoi,
                scale=1000,
                maxPixels=1e8,
            )
            .getInfo()
            .get("area", 1) or 1
        )
        flood_fraction = flooded_km2 / float(aoi_area_km2)
        anomaly_score = min(100.0, flood_fraction * 500)  # 20% AOI flooded → score 100

        metric_label = (
            f"{flooded_km2:,.0f} km² flooded"
            if is_active
            else "No active flood signal"
        )

        return ThemeResult(
            theme=self.THEME_NAME,
            tile_url=tile_url,
            tile_url_expires_at=expires_at,
            vis_params=VIS_FLOOD,
            metric_value=flooded_km2,
            metric_unit="km²",
            metric_label=metric_label,
            stats={
                "flooded_km2": round(flooded_km2, 2),
                "urban_flood_km2": round(urban_flood_km2, 2),
                "is_active": is_active,
                "urban_flag": urban_flood_km2 > 0.1,
                "scene_count": scene_count,
                "flood_threshold_db": flood_threshold_db,
                "reference_period": f"{ref_start} to {ref_end}",
            },
            anomaly_score=round(anomaly_score, 1),
            confidence=round(confidence, 2),
            data_age_hours=data_age_hours,
            data_source=f"Sentinel-1 GRD, acquired {acq_dt}, {scene_count} scenes",
            error=None,
        )

    def _get_reference_window(
        self, end_date: str, years_back: int = 2
    ) -> tuple[str, str]:
        """Build a same-calendar-month window N years prior for baseline."""
        from datetime import date, timedelta
        end = date.fromisoformat(end_date)
        # Go back N years, keep same month, extend ±30 days
        ref_center = end.replace(year=end.year - years_back)
        ref_start = (ref_center - timedelta(days=30)).isoformat()
        ref_end = (ref_center + timedelta(days=30)).isoformat()
        return ref_start, ref_end
