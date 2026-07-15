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
        tidal_zone_widen_capped = False  # may be set True in the 30d->90d widen check below

        # ── Current: Dynamic World 10-day majority composite ─────────────────
        def _dw_col(s: str, e: str):
            return (
                ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
                .filterBounds(aoi)
                .filterDate(s, e)
                .select("label")
            )

        dw_current = _dw_col(start_date, end_date)
        dw_count = dw_current.size().getInfo()

        if dw_count == 0:
            # Widen +15 days
            start_dt = date.fromisoformat(start_date)
            w15_start = (start_dt - timedelta(days=15)).isoformat()
            log.info("landuse.fallback_dw_widen_15d", start=w15_start, end=end_date)
            dw_current = _dw_col(w15_start, end_date)
            dw_count = dw_current.size().getInfo()

            if dw_count == 0:
                # Widen +30 days
                w30_start = (start_dt - timedelta(days=30)).isoformat()
                log.info("landuse.fallback_dw_widen_30d", start=w30_start, end=end_date)
                dw_current = _dw_col(w30_start, end_date)
                dw_count = dw_current.size().getInfo()

                if dw_count == 0:
                    # Before widening to 90d, check whether this is a tidal/deltaic
                    # AOI (WorldCover class 90 = wetland, 95 = mangrove). A 90-day
                    # window mixes multiple tide states and possibly a wet/dry season
                    # boundary, causing mudflats and cleared mangrove to be over-counted
                    # as "built" (class 6) in the MODE composite.
                    # Cap at 30d for tidal zones to avoid this classification artefact.
                    _wc = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
                    _tidal_stats = gee_client.get_stats(
                        image=_wc.eq(90).Or(_wc.eq(95)).rename("tidal_frac"),
                        aoi=aoi, scale=100, reducer=ee.Reducer.mean(), max_pixels=1e9,
                    )
                    _tidal_frac = float(_tidal_stats.get("tidal_frac") or 0.0)
                    tidal_zone_widen_capped = _tidal_frac > 0.10

                    if tidal_zone_widen_capped:
                        # Tidal/mangrove AOI: cap widening at 30d already done above;
                        # do NOT widen to 90d — return with dw_count==0 to fall through
                        # to the ESA WorldCover static fallback.
                        log.info(
                            "landuse.tidal_zone_widen_capped",
                            tidal_frac=round(_tidal_frac, 3),
                            reason="WorldCover wetland/mangrove >10%; 90d window suppressed",
                        )
                        # Fall through to ESA WorldCover static fallback (dw_count==0 path)
                    else:
                        # Non-tidal zone: widen +90 days as before
                        w90_start = (start_dt - timedelta(days=90)).isoformat()
                        log.info("landuse.fallback_dw_widen_90d", start=w90_start, end=end_date)
                        dw_current = _dw_col(w90_start, end_date)
                        dw_count = dw_current.size().getInfo()

                    if dw_count == 0:
                        # All Dynamic World tiers exhausted: fall back to ESA WorldCover
                        # alone as a static 2021 land-cover map. No temporal "change"
                        # can be detected, but we can still report the land-cover
                        # composition and Hansen GFW deforestation. The confidence
                        # penalty reflects absence of a dynamic current layer.
                        log.warning(
                            "landuse.fallback_worldcover_only",
                            reason="No Dynamic World scenes across any fallback window (15/30/90d)",
                        )
                        # Use ESA WorldCover as both current and baseline (no-change proxy)
                        esa_static = (
                            ee.ImageCollection("ESA/WorldCover/v200")
                            .first()
                            .select("Map")
                            .rename("label")
                        )
                        # Re-map ESA to DW-compatible classes for change matrix below
                        esa_as_dw = esa_static.remap(
                            [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100],
                            [1,  5,  2,  4,  6,  7,  8,  0,  3,  3,  2],
                        ).rename("label")
                        dw_current = ee.ImageCollection([esa_as_dw])
                        dw_count = 0  # signal: static fallback, no dynamic scenes
                        dw_source = "ESA WorldCover v200 (static — no Dynamic World coverage)"
                    else:
                        dw_source = f"Dynamic World (widened 90d: {w90_start}→{end_date})"
                else:
                    dw_source = f"Dynamic World (widened 30d: {w30_start}→{end_date})"
            else:
                dw_source = f"Dynamic World (widened 15d: {w15_start}→{end_date})"
        else:
            dw_source = f"Dynamic World ({start_date}→{end_date})"

        # Majority class composite
        current_label = dw_current.mode().rename("current_class")
        # Confidence: static WorldCover fallback = 0.30 (no temporal comparison),
        # otherwise scale with number of DW scenes available.
        if dw_count == 0:
            confidence = 0.30  # static ESA WorldCover — no change detection possible
        else:
            confidence = min(1.0, 0.6 + dw_count * 0.05)
            tidal_zone_widen_capped = False

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

        # Exclude wetland/mangrove-ORIGIN pixels from natural_to_built to avoid
        # counting tidal geomorphology as "urban expansion" in deltaic AOIs.
        # Track the excluded area separately (wetland_to_built_ha) -- never silently
        # discard the signal, just correctly label it.
        esa_is_wetland_or_mangrove = esa_baseline.eq(90).Or(esa_baseline.eq(95))
        natural_to_built = (
            esa_remapped.lte(3)
            .And(current_label.eq(6))
            .And(esa_is_wetland_or_mangrove.Not())
        )
        wetland_to_built = esa_is_wetland_or_mangrove.And(current_label.eq(6))

        def area_ha(mask: "ee.Image") -> float:
            s = gee_client.get_stats(
                image=mask.multiply(pixel_area_ha).rename("area"),
                aoi=aoi, scale=30, reducer=ee.Reducer.sum(),
            )
            return float(s.get("area", 0) or 0)

        tree_to_built_ha = area_ha(tree_to_built)
        tree_to_crops_ha = area_ha(tree_to_crops)
        wetland_to_bare_ha = area_ha(wetland_to_bare)
        wetland_to_built_ha = area_ha(wetland_to_built)   # NEW: tracked separately, not discarded
        total_natural_to_built = area_ha(natural_to_built)  # excludes wetland/mangrove origin
        changed_area_ha = tree_to_built_ha + tree_to_crops_ha + wetland_to_bare_ha

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

        # ── Runoff coefficient change (USDA CN-based) ─────────────────────────
        # Rough estimate: tree→built increases CN by ~40 units → runoff ↑ ~17%
        # Scaled by proportion of changed area
        aoi_area_stats = gee_client.get_stats(
            image=ee.Image.pixelArea().divide(10000).rename("area"),
            aoi=aoi, scale=100, reducer=ee.Reducer.sum(),
        )
        aoi_area_ha = float(aoi_area_stats.get("area", 1) or 1)
        runoff_increase_pct = (
            (tree_to_built_ha / aoi_area_ha) * 40.0  # 40% runoff increase per deforested ha→built
            + (tree_to_crops_ha / aoi_area_ha) * 15.0  # crops less impervious
        )

        # ── Tile URL: current Dynamic World label ─────────────────────────────
        tile_url, expires_at = gee_client.get_tile_url(current_label.clip(aoi), VIS_LANDUSE)

        anomaly_score = min(100.0, changed_area_ha / max(aoi_area_ha, 1) * 1000)

        return ThemeResult(
            theme=self.THEME_NAME,
            tile_url=tile_url,
            tile_url_expires_at=expires_at,
            vis_params=VIS_LANDUSE,
            metric_value=changed_area_ha,
            metric_unit="ha",
            metric_label=f"{changed_area_ha:,.1f} ha land use change detected",
            stats={
                "changed_area_ha": round(changed_area_ha, 1),
                "transitions": {
                    "tree_to_built_ha": round(tree_to_built_ha, 1),
                    "tree_to_crops_ha": round(tree_to_crops_ha, 1),
                    "wetland_to_bare_ha": round(wetland_to_bare_ha, 1),
                    "natural_to_built_ha": round(total_natural_to_built, 1),
                    "wetland_to_built_ha": round(wetland_to_built_ha, 1),
                },
                "deforestation_ha": round(deforestation_ha, 1),
                "urban_expansion_ha": round(tree_to_built_ha, 1),
                "runoff_increase_pct": round(runoff_increase_pct, 1),
                "catchment_impact": (
                    f"Runoff increased ~{runoff_increase_pct:.0f}%, sediment load elevated"
                    if runoff_increase_pct > 5 else "Minimal catchment impact"
                ),
                "dw_scene_count": dw_count,
                "tidal_zone_widen_capped": tidal_zone_widen_capped,
            },
            anomaly_score=round(anomaly_score, 1),
            confidence=round(confidence, 2),
            data_age_hours=24.0,  # Dynamic World near-daily
            data_source=f"{dw_source} + ESA WorldCover v200 (2021 baseline) + Hansen GFW v1.11 (loss through 2023), {end_date}",
            error=None,
        )
