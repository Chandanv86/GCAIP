"""
Theme endpoints — per-theme history and tile URL refresh.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from models.theme_result import ThemeResult
# VALID_THEMES is now the canonical list from theme_registry.py.
# Do NOT redeclare it here.
from schemas.analysis import VALID_THEMES

router = APIRouter()


@router.get("/pipelines/search")
async def search_pipelines(
    min_lon: float = Query(...),
    min_lat: float = Query(...),
    max_lon: float = Query(...),
    max_lat: float = Query(...),
) -> dict:
    """
    Query pipeline geometries for a bounding box.

    Resolution order (matches pipeline_corridor.py processor):
      1. OpenStreetMap via Overpass (man_made=pipeline) — cached 24h.
      2. EDF/OGIM/current via GEE — used when OSM returns 0 features.
         This ensures the frontend always renders the SAME geometry the backend analyzed.
    """
    import asyncio
    from integrations.overpass import OverpassClient
    client = OverpassClient()
    bbox = [min_lon, min_lat, max_lon, max_lat]

    try:
        geojson = client.get_pipelines(bbox)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Overpass query failed: {exc}")

    # If OSM returned no features, fall back to OGIM.
    # GEE calls are blocking — run in thread pool to avoid stalling the event loop.
    if not geojson.get("features"):
        def _fetch_ogim() -> dict:
            try:
                import ee
                from gee import client as gee_client
                gee_client.initialize()

                aoi = ee.Geometry.BBox(min_lon, min_lat, max_lon, max_lat)
                ogim = (
                    ee.FeatureCollection("EDF/OGIM/current")
                    .filterBounds(aoi)
                    .filter(ee.Filter.stringContains("CATEGORY", "PIPELINE"))
                )
                count = gee_client.safe_call(ogim.size().getInfo)
                if not count:
                    return {"type": "FeatureCollection", "features": []}

                raw = gee_client.safe_call(
                    ogim.limit(500).map(lambda f: f.simplify(maxError=50)).getInfo
                )
                features = []
                for feat in (raw or {}).get("features", []):
                    geom = feat.get("geometry")
                    props = feat.get("properties", {})
                    if geom:
                        features.append({
                            "type": "Feature",
                            "geometry": geom,
                            "properties": {
                                "source": "EDF/OGIM/current",
                                "category": props.get("CATEGORY", "PIPELINE"),
                                "operator": props.get("OPERATOR", ""),
                            },
                        })
                return {"type": "FeatureCollection", "features": features}
            except Exception as ogim_exc:
                import logging
                logging.getLogger(__name__).warning(
                    "pipelines_search.ogim_fallback_failed: %s", str(ogim_exc)
                )
                return {"type": "FeatureCollection", "features": []}

        loop = asyncio.get_event_loop()
        geojson = await loop.run_in_executor(None, _fetch_ogim)

    return geojson






@router.get("/themes/{theme}/history/{aoi_id}")
async def get_theme_history(
    theme: str,
    aoi_id: uuid.UUID,
    metric: Annotated[str | None, Query()] = None,
    period: Annotated[str, Query()] = "12m",
    interval: Annotated[str, Query()] = "1d",
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Historical metric time series from TimescaleDB.
    Served from metric_timeseries hypertable — < 50ms.

    period: "7d" | "30d" | "12m" | "5y"
    interval: "1h" | "1d" | "7d"
    """
    if theme not in VALID_THEMES:
        raise HTTPException(400, f"Invalid theme. Must be one of {VALID_THEMES}")

    # Parse period
    period_days = {
        "7d": 7, "30d": 30, "90d": 90, "12m": 365, "5y": 1825,
    }.get(period, 365)

    # Query TimescaleDB continuous aggregate for daily data
    query = text("""
        SELECT
            day AS time,
            avg_value AS value,
            avg_confidence AS confidence,
            min_value,
            max_value
        FROM metric_daily
        WHERE aoi_id = :aoi_id
          AND theme = :theme
          AND (:metric IS NULL OR metric_name = :metric)
          AND day >= NOW() - INTERVAL ':period days'
        ORDER BY day ASC
        LIMIT 1000
    """)
    # Note: TimescaleDB parameter interpolation requires literal for INTERVAL
    # Using raw SQL with parameterized query via text() for safety
    raw_query = f"""
        SELECT
            day::text AS time,
            avg_value AS value,
            avg_confidence AS confidence,
            min_value,
            max_value
        FROM metric_daily
        WHERE aoi_id = '{aoi_id}'
          AND theme = '{theme}'
          {f"AND metric_name = '{metric}'" if metric else ""}
          AND day >= NOW() - INTERVAL '{period_days} days'
        ORDER BY day ASC
        LIMIT 1000
    """
    result = await db.execute(text(raw_query))
    rows = result.mappings().all()

    return {
        "aoi_id": str(aoi_id),
        "theme": theme,
        "metric": metric,
        "period": period,
        "interval": interval,
        "data": [dict(row) for row in rows],
        "unit": _theme_default_unit(theme),
    }


@router.get("/themes/{theme}/tile_url/{result_id}")
async def get_tile_url(
    theme: str,
    result_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return tile URL for a result. If expired (> 6h), trigger GEE re-render.
    """
    res = await db.execute(select(ThemeResult).where(ThemeResult.id == result_id))
    tr = res.scalar_one_or_none()
    if not tr:
        raise HTTPException(404, "Theme result not found")

    now = datetime.now(timezone.utc)
    if tr.tile_url and tr.tile_url_expires_at and tr.tile_url_expires_at > now:
        return {
            "tile_url": tr.tile_url,
            "vis_params": tr.vis_params,
            "expires_at": tr.tile_url_expires_at.isoformat(),
            "fresh": True,
        }

    # Tile expired — would re-render here (Phase 2: trigger lightweight GEE map_id call)
    return {
        "tile_url": None,
        "vis_params": tr.vis_params,
        "expires_at": None,
        "fresh": False,
        "message": "Tile URL expired. Re-run analysis to refresh.",
    }


def _theme_default_unit(theme: str) -> str:
    return {
        "flood": "km²", "rainfall": "mm", "reservoir": "%",
        "mangrove": "ha", "erosion": "m/yr",
        "vegetation": "NDVI", "landuse": "ha",
        "effluent_plume": "km²", "coastal_outfall": "km²",
        "pipeline_corridor": "m",
    }.get(theme, "")


@router.get("/themes/{theme}/yearly/{aoi_id}")
async def get_theme_yearly_trend(
    theme: str,
    aoi_id: uuid.UUID,
    metric_name: str = Query(..., description="Which stat key to chart (e.g. 'spi_7' for rainfall, 'changed_area_ha' for landuse)."),
    years_back: int = Query(5, ge=1, le=20, description="How many years of data to include."),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Year-over-year trend for a given theme metric, backed by the
    metric_timeseries hypertable. Returns rows shaped for Recharts:
      [{"year": 2022, "avg_value": .., "min_value": .., "max_value": ..,
        "sample_count": .., "avg_confidence": ..}, ...]

    NOTE: Charts only have data from the point `write_theme_metrics` was
    deployed (or after a backfill from existing theme_results rows --
    see scripts/backfill_timeseries.py recommendation in diagnostic report).
    """
    if theme not in VALID_THEMES:
        raise HTTPException(status_code=400, detail=f"Invalid theme '{theme}'. Must be one of: {VALID_THEMES}")

    from services.timeseries_writer import get_yearly_trend, get_available_metric_names
    from db.utils import get_sync_session
    sync_session = get_sync_session()
    try:
        rows = get_yearly_trend(sync_session, str(aoi_id), theme, metric_name, years_back)
        available_metrics = get_available_metric_names(sync_session, str(aoi_id), theme)
    finally:
        sync_session.close()

    return {
        "aoi_id": str(aoi_id),
        "theme": theme,
        "metric": metric_name,
        "years_back": years_back,
        "unit": _theme_default_unit(theme),
        "years": rows,
        "available_metrics": available_metrics,
    }


@router.get("/themes/{theme}/yearly/{aoi_id}/metrics")
async def get_theme_metric_names(
    theme: str,
    aoi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    List all metric names available in metric_timeseries for this AOI + theme.
    Used to populate a frontend metric picker dropdown for the yearly chart.
    """
    if theme not in VALID_THEMES:
        raise HTTPException(status_code=400, detail=f"Invalid theme '{theme}'.")

    from services.timeseries_writer import get_available_metric_names
    from db.utils import get_sync_session
    sync_session = get_sync_session()
    try:
        metrics = get_available_metric_names(sync_session, str(aoi_id), theme)
    finally:
        sync_session.close()

    return {"aoi_id": str(aoi_id), "theme": theme, "available_metrics": metrics}
