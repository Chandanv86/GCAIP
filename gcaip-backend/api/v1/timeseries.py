"""Time-series data endpoint — served from TimescaleDB."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db

router = APIRouter()


@router.get("/timeseries/{aoi_id}")
async def get_timeseries(
    aoi_id: uuid.UUID,
    themes: Annotated[str | None, Query()] = None,  # comma-separated
    metric: Annotated[str | None, Query()] = None,
    days: Annotated[int, Query(ge=7, le=1825)] = 365,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return multi-theme time series for a given AOI.
    Used by the dashboard charts (Recharts).
    """
    theme_filter = ""
    if themes:
        theme_list = ", ".join(f"'{t.strip()}'" for t in themes.split(","))
        theme_filter = f"AND theme IN ({theme_list})"

    raw = f"""
        SELECT
            day::text         AS time,
            theme,
            metric_name,
            avg_value         AS value,
            avg_confidence    AS confidence,
            min_value,
            max_value
        FROM metric_daily
        WHERE aoi_id = '{aoi_id}'
          {theme_filter}
          {f"AND metric_name = '{metric}'" if metric else ""}
          AND day >= NOW() - INTERVAL '{days} days'
        ORDER BY theme, day ASC
        LIMIT 5000
    """
    result = await db.execute(text(raw))
    rows = result.mappings().all()

    # Group by theme for frontend consumption
    grouped: dict[str, list] = {}
    for row in rows:
        t = row["theme"]
        if t not in grouped:
            grouped[t] = []
        grouped[t].append({
            "time": row["time"],
            "value": row["value"],
            "confidence": row["confidence"],
            "min": row["min_value"],
            "max": row["max_value"],
            "metric": row["metric_name"],
        })

    return {
        "aoi_id": str(aoi_id),
        "days": days,
        "themes": grouped,
    }
