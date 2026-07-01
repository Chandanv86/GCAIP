"""Alert endpoints — list active alerts, resolve alerts, subscribe."""
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from models.alert import Alert

router = APIRouter()


@router.get("/alerts")
async def list_alerts(
    aoi_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[str, Query()] = "active",
    severity: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List alerts, optionally filtered by AOI, status, and severity."""
    q = select(Alert).order_by(Alert.triggered_at.desc())
    if aoi_id:
        q = q.where(Alert.aoi_id == aoi_id)
    if status:
        q = q.where(Alert.status == status)
    if severity:
        q = q.where(Alert.severity == severity)

    offset = (page - 1) * page_size
    result = await db.execute(q.offset(offset).limit(page_size))
    alerts = result.scalars().all()

    return {
        "items": [_alert_dict(a) for a in alerts],
        "page": page,
        "page_size": page_size,
    }


@router.get("/alerts/{alert_id}")
async def get_alert(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "Alert not found")
    return _alert_dict(alert)


@router.post("/alerts/{alert_id}/resolve", status_code=200)
async def resolve_alert(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mark an alert as resolved."""
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.status = "resolved"
    alert.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "resolved", "alert_id": str(alert_id)}


def _alert_dict(alert: Alert) -> dict:
    return {
        "id": str(alert.id),
        "aoi_id": str(alert.aoi_id),
        "severity": alert.severity,
        "theme": alert.theme,
        "alert_type": alert.alert_type,
        "title": alert.title,
        "message": alert.message,
        "metric_value": alert.metric_value,
        "metric_unit": alert.metric_unit,
        "tile_url": alert.tile_url,
        "status": alert.status,
        "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else None,
        "expires_at": alert.expires_at.isoformat() if alert.expires_at else None,
        "email_sent": alert.email_sent,
    }
