"""
GCAIP Theme 7 — Land Use Change Processor

Algorithm: Dynamic World (current) vs ESA WorldCover v200 (2021 baseline)
Detects class transitions: tree→built, tree→crops, wetland→bare, etc.
Also uses Hansen GFW for confirmed forest loss alerts.
"""
import structlog
from datetime import date, timedelta

import ee

from gee import client as gee_client
from gee.processors.base import BaseThemeProcessor, ThemeResult

log = structlog.get_logger(__name__)

# Dynamic World class IDs
DW_CLASSES = {
    0: "water", 1: "trees", 2: "grass", 3: "flooded_vegetation",
    4: "crops", 5: "shrub_and_scrub", 6: "built", 7: "bare", 8: "snow_and_ice",
}

# ESA WorldCover class IDs
ESA_CLASSES = {
    10: "tree_cover", 20: "shrubland", 30: "grassland", 40: "cropland",
    50: "built_up", 60: "bare_sparse", 70: "snow_ice",
    80: "permanent_water", 90: "herbaceous_wetland", 95: "mangroves", 100: "moss",
}

VIS_LANDUSE = {
    "min": 0,
    "max": 8,
    "palette": [
        "#419BDF",  # water
        "#397D49",  # trees
        "#88B053",  # grass
        "#7A87C6",  # flooded veg
        "#E49635",  # crops
        "#DFC35A",  # shrub
        "#C4281B",  # built (highlight)
        "#A59B8F",  # bare
        "#B39FE1",  # snow
    ],
}


class LandUseProcessor(BaseThemeProcessor):
    THEME_NAME = "landuse"

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
            log.error("landuse.compute_error", error=str(exc))
            return ThemeResult.error_result(self.THEME_NAME, str(exc))

    def _run_gee_analysis(
        self, aoi: "ee.Geometry", start_date: str, end_date: str
    ) -> ThemeResult:
        end = date.fromisoformat(end_date)

        # ── Current: Dynamic World — expand window progressively if needed ────
        dw_current = None
        dw_count = 0
        dw_window_days = 30  # start with the default 30-day window

        for window in [30, 90, 180]:
            dw_start = (end - timedelta(days=window)).isoformat()
            dw_col = (
                ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
                .filterBounds(aoi)
                .filterDate(dw_start, end_date)
                .select("label")
            )
            dw_count = dw_col.size().getInfo()
            if dw_count > 0:
                dw_current = dw_col
                dw_window_days = window
                break

        if dw_current is None or dw_count == 0:
            raise gee_client.GEEAssetNotFoundError(
                f"No Dynamic World images found for any window up to 180 days before {end_date}"
            )

        # Majority class composite
        current_label = dw_current.mode().rename("current_class")
        confidence = min(1.0, 0.6 + dw_count * 0.05)

        # ── Baseline: ESA WorldCover v200 (2021) ─────────────────────────────
        esa_baseline = (
            ee.ImageCollection("ESA/WorldCover/v200")
            .first()
            .select("Map")
            .rename("baseline_class")
        )

        # Remap ESA → DW-compatible labels (tree=1, built=6, crops=4)
        # Key mappings for change detection
        esa_remapped = esa_baseline.remap(
            [10, 20, 30, 40, 50, 60, 80, 90, 95],
            [1,  5,  2,  4,  6,  7,  0,  3,  3],  # DW-equivalent classes
        ).rename("esa_dw_equiv")

        # ── Change matrix ─────────────────────────────────────────────────────
        pixel_area_ha = ee.Image.pixelArea().divide(10000)

        # High-priority transitions
        tree_to_built = esa_remapped.eq(1).And(current_label.eq(6))
        tree_to_crops = esa_remapped.eq(1).And(current_label.eq(4))
        wetland_to_bare = esa_remapped.eq(3).And(current_label.eq(7))
        natural_to_built = esa_remapped.lte(3).And(current_label.eq(6))

        def area_ha(mask: "ee.Image") -> float:
            s = gee_client.get_stats(
                image=mask.multiply(pixel_area_ha).rename("area"),
                aoi=aoi, scale=30, reducer=ee.Reducer.sum(),
            )
            return float(s.get("area", 0) or 0)

        tree_to_built_ha = area_ha(tree_to_built)
        tree_to_crops_ha = area_ha(tree_to_crops)
        wetland_to_bare_ha = area_ha(wetland_to_bare)
        total_natural_to_built = area_ha(natural_to_built)
        dw_changed_area_ha = tree_to_built_ha + tree_to_crops_ha + wetland_to_bare_ha

        # ── Hansen GFW forest loss layer ──────────────────────────────────────
        try:
            # UMD Hansen GFW: 'lossyear' = year of loss (1-23 for 2001-2023)
            hansen = ee.Image(
                "UMD/hansen/global_forest_change_2023_v1_11"
            ).select("lossyear")
            # Hansen lossyear encoding: 1=2001, 23=2023 (dataset ends at 2023)
            # Always use the last 3 available years of the dataset (2021-2023)
            HANSEN_MAX_YEAR = 23  # Update when new Hansen version released
            HANSEN_RECENT_YEARS = 3
            recent_loss = hansen.gte(HANSEN_MAX_YEAR - HANSEN_RECENT_YEARS + 1).And(
                hansen.lte(HANSEN_MAX_YEAR)
            )
            deforestation_ha = area_ha(recent_loss)
        except Exception as gfw_exc:
            log.warning("landuse.hansen_error", error=str(gfw_exc))
            deforestation_ha = 0.0

        # Total changed area = DW transitions + Hansen deforestation (avoid double-counting)
        # Hansen captures forest loss that DW may miss (different spatial/temporal resolution)
        changed_area_ha = dw_changed_area_ha + max(0.0, deforestation_ha - tree_to_crops_ha)

        # ── Runoff coefficient change (USDA CN-based) ─────────────────────────
        # Rough estimate: tree→built increases CN by ~40 units → runoff ↑ ~17%
        # Include deforestation in runoff impact (cleared forest increases runoff)
        aoi_area_stats = gee_client.get_stats(
            image=ee.Image.pixelArea().divide(10000).rename("area"),
            aoi=aoi, scale=100, reducer=ee.Reducer.sum(),
        )
        aoi_area_ha = float(aoi_area_stats.get("area", 1) or 1)
        runoff_increase_pct = (
            (tree_to_built_ha / aoi_area_ha) * 40.0  # 40% runoff increase per deforested ha→built
            + (tree_to_crops_ha / aoi_area_ha) * 15.0  # crops less impervious
            + (deforestation_ha / aoi_area_ha) * 20.0  # general forest loss → runoff
        )

        # ── Tile URL: current Dynamic World label ─────────────────────────────
        tile_url, expires_at = gee_client.get_tile_url(current_label, VIS_LANDUSE)

        anomaly_score = min(100.0, changed_area_ha / max(aoi_area_ha, 1) * 1000)

        log.info(
            "landuse.computed",
            dw_window_days=dw_window_days,
            dw_scene_count=dw_count,
            dw_changed_ha=round(dw_changed_area_ha, 1),
            hansen_deforestation_ha=round(deforestation_ha, 1),
            total_changed_ha=round(changed_area_ha, 1),
        )

        return ThemeResult(
            theme=self.THEME_NAME,
            tile_url=tile_url,
            tile_url_expires_at=expires_at,
            vis_params=VIS_LANDUSE,
            metric_value=changed_area_ha,
            metric_unit="ha",
            metric_label=f"{changed_area_ha:,.0f} ha land use change detected",
            stats={
                "changed_area_ha": round(changed_area_ha, 1),
                "transitions": {
                    "tree_to_built_ha": round(tree_to_built_ha, 1),
                    "tree_to_crops_ha": round(tree_to_crops_ha, 1),
                    "wetland_to_bare_ha": round(wetland_to_bare_ha, 1),
                    "natural_to_built_ha": round(total_natural_to_built, 1),
                },
                "deforestation_ha": round(deforestation_ha, 1),
                "urban_expansion_ha": round(total_natural_to_built, 1),
                "runoff_increase_pct": round(runoff_increase_pct, 1),
                "catchment_impact": (
                    f"Runoff increased ~{runoff_increase_pct:.0f}%, sediment load elevated"
                    if runoff_increase_pct > 5 else "Minimal catchment impact"
                ),
                "dw_scene_count": dw_count,
                "dw_window_days": dw_window_days,
            },
            anomaly_score=round(anomaly_score, 1),
            confidence=round(confidence, 2),
            data_age_hours=24.0,  # Dynamic World near-daily
            data_source=f"Dynamic World V1 ({dw_window_days}d window) + ESA WorldCover v200 (2021 baseline) + Hansen GFW v1.11 (loss through 2023), {end_date}",
            error=None,
        )
