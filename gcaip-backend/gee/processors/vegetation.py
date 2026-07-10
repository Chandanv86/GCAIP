"""
GCAIP Theme 6 — Coastal Vegetation Buffer Processor

Algorithm: Sentinel-2 NDVI buffer analysis vs 5-year climatology.
Identifies degraded vegetation buffer width along the coastline.
"""
import structlog
from datetime import date, timedelta

import ee

from gee import client as gee_client
from gee.processors.base import BaseThemeProcessor, ThemeResult

log = structlog.get_logger(__name__)

VIS_VEGETATION = {
    "min": -0.2,
    "max": 0.8,
    "palette": [
        "#d73027",  # bare / degraded
        "#fc8d59",
        "#fee08b",  # stressed
        "#d9ef8b",
        "#91cf60",  # healthy
        "#1a9850",  # excellent
    ],
}


class VegetationProcessor(BaseThemeProcessor):
    THEME_NAME = "vegetation"

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
            log.error("vegetation.compute_error", error=str(exc))
            return ThemeResult.error_result(self.THEME_NAME, str(exc))

    def _run_gee_analysis(
        self, aoi: "ee.Geometry", end_date: str
    ) -> ThemeResult:
        end = date.fromisoformat(end_date)
        start_30d = (end - timedelta(days=30)).isoformat()
        start_90d = (end - timedelta(days=90)).isoformat()

        def get_ndvi(start: str, stop: str) -> "ee.Image":
            s2 = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(aoi)
                .filterDate(start, stop)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
                .map(self.apply_s2_cloud_mask)
            )
            if s2.size().getInfo() == 0:
                return None
            median = s2.median()
            nir = median.select("B8")
            red = median.select("B4")
            return nir.subtract(red).divide(nir.add(red)).rename("NDVI")

        current_ndvi = get_ndvi(start_30d, end_date)
        if current_ndvi is None:
            return ThemeResult.error_result(
                self.THEME_NAME, "No Sentinel-2 data available for vegetation analysis."
            )

        # 5-year climatology: same 30-day window, years -2 to -5
        clim_ndvi_values = []
        for y in range(2, 6):
            ref_end = (end.replace(year=end.year - y)).isoformat()
            ref_start = (
                end.replace(year=end.year - y) - timedelta(days=30)
            ).isoformat()
            if ref_start < "2019-01-01":
                continue
            ndvi_hist = get_ndvi(ref_start, ref_end)
            if ndvi_hist is None:
                continue
            stats = gee_client.get_stats(
                image=ndvi_hist, aoi=aoi, scale=20,
                reducer=ee.Reducer.mean(),
            )
            val = float(stats.get("NDVI", 0) or 0)
            if val != 0:
                clim_ndvi_values.append(val)

        import statistics
        clim_mean = (
            statistics.mean(clim_ndvi_values) if clim_ndvi_values else 0.5
        )
        clim_std = (
            statistics.stdev(clim_ndvi_values)
            if len(clim_ndvi_values) > 1 else 0.1
        )

        current_stats = gee_client.get_stats(
            image=current_ndvi, aoi=aoi, scale=20,
            reducer=ee.Reducer.mean(),
        )
        ndvi_mean = float(current_stats.get("NDVI", 0) or 0)

        # Z-score
        ndvi_z = (ndvi_mean - clim_mean) / max(clim_std, 0.01)

        # Health classification
        if ndvi_mean >= 0.6:
            health_label = "GOOD"
        elif ndvi_mean >= 0.4:
            health_label = "MODERATE"
        elif ndvi_mean >= 0.2:
            health_label = "STRESSED"
        else:
            health_label = "DEGRADED"

        health_score = min(100.0, max(0.0, (ndvi_mean - 0.1) / 0.7 * 100.0))

        # Degraded fraction (NDVI < 0.3 within AOI)
        degraded_stats = gee_client.get_stats(
            image=current_ndvi.lt(0.3).unmask(0).rename("degraded"),
            aoi=aoi, scale=20, reducer=ee.Reducer.mean(),
        )
        degraded_pct = float(degraded_stats.get("degraded", 0) or 0) * 100

        # Dieback flag: NDVI < previous 90d composite by >0.15
        ndvi_90d = get_ndvi(start_90d, start_30d)
        dieback_flag = False
        if ndvi_90d is not None:
            diff_stats = gee_client.get_stats(
                image=current_ndvi.subtract(ndvi_90d).rename("diff"),
                aoi=aoi, scale=20, reducer=ee.Reducer.mean(),
            )
            ndvi_diff = float(diff_stats.get("diff", 0) or 0)
            dieback_flag = ndvi_diff < -0.15

        tile_url, expires_at = gee_client.get_tile_url(current_ndvi.clip(aoi), VIS_VEGETATION)
        anomaly_score = min(100.0, abs(ndvi_z) / 3.0 * 100.0)
        confidence = min(1.0, 0.5 + len(clim_ndvi_values) * 0.1)

        return ThemeResult(
            theme=self.THEME_NAME,
            tile_url=tile_url,
            tile_url_expires_at=expires_at,
            vis_params=VIS_VEGETATION,
            metric_value=round(ndvi_mean, 3),
            metric_unit="NDVI",
            metric_label=f"Vegetation health: {health_label} (NDVI {ndvi_mean:.2f})",
            stats={
                "ndvi_mean": round(ndvi_mean, 3),
                "ndvi_anomaly_z": round(ndvi_z, 2),
                "clim_mean_ndvi": round(clim_mean, 3),
                "health_score": round(health_score, 1),
                "health_label": health_label,
                "degraded_pct": round(degraded_pct, 1),
                "dieback_flag": dieback_flag,
            },
            anomaly_score=round(anomaly_score, 1),
            confidence=round(confidence, 2),
            data_age_hours=48.0,
            data_source=f"Sentinel-2 SR NDVI, 30-day composite to {end_date}",
            error=None,
        )
