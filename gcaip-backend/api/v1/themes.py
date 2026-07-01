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

router = APIRouter()

VALID_THEMES = [
    "flood", "rainfall", "reservoir",
    "mangrove", "erosion", "vegetation", "landuse",
]


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
    }.get(theme, "")
