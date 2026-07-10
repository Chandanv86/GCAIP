"""
Alert and scheduling Celery tasks.
  - scheduled_reanalysis: Celery Beat triggers re-analysis of all registered AOIs
  - evaluate_alerts_task: Checks thresholds after each analysis run
  - cleanup_expired_tiles: Removes stale GEE tile URLs from Redis
"""
import logging
from datetime import datetime, timezone, timedelta

from workers.celery_app import celery_app
from db.utils import get_sync_session as _get_sync_session

import structlog
log = structlog.get_logger(__name__)


@celery_app.task(name="workers.tasks.alert_tasks.evaluate_alerts_task",
                 queue="alert_tasks")
def evaluate_alerts_task(run_id: str) -> dict:
    """
    Evaluate alert thresholds after a run completes.
    Creates Alert records for any breached thresholds.
    """
    from services.alert_engine import AlertEngine
    from models.theme_result import ThemeResult as ThemeResultModel
    from models.analysis_run import AnalysisRun
    from config import settings

    if not settings.ENABLE_SCHEDULED_ANALYSIS:
        return {}

    session = _get_sync_session()
    try:
        run = session.query(AnalysisRun).filter_by(id=run_id).first()
        if not run:
            return {}

        theme_results = (
            session.query(ThemeResultModel)
            .filter_by(run_id=run_id)
            .all()
        )

        engine = AlertEngine()
        alerts_created = engine.evaluate(
            aoi_id=str(run.aoi_id),
            run_id=run_id,
            theme_results={r.theme: r for r in theme_results},
            session=session,
        )

        if alerts_created and settings.ENABLE_EMAIL_ALERTS:
            for alert in alerts_created:
                dispatch_email_alert_task.delay(str(alert.id))

        return {"alerts_created": len(alerts_created)}
    finally:
        session.close()


@celery_app.task(name="workers.tasks.alert_tasks.dispatch_email_alert_task",
                 queue="alert_tasks")
def dispatch_email_alert_task(alert_id: str) -> dict:
    """Send email notification for a specific alert."""
    from integrations.sendgrid_client import SendGridClient
    from models.alert import Alert

    session = _get_sync_session()
    try:
        alert = session.query(Alert).filter_by(id=alert_id).first()
        if not alert or alert.email_sent:
            return {}

        client = SendGridClient()
        success = client.send_alert_email(alert)
        if success:
            alert.email_sent = True
            alert.dispatched_at = datetime.now(timezone.utc)
            session.commit()
        return {"sent": success}
    finally:
        session.close()


@celery_app.task(name="workers.tasks.alert_tasks.scheduled_reanalysis",
                 queue="alert_tasks")
def scheduled_reanalysis(triggered_by: str = "schedule") -> dict:
    """
    Celery Beat job: re-analyze all public/registered AOIs.
    Runs every 6 hours at off-peak UTC.
    """
    from models.aoi import AOI
    from services.orchestrator import AnalysisOrchestrator
    from config import settings

    if not settings.ENABLE_SCHEDULED_ANALYSIS:
        return {"skipped": True}

    session = _get_sync_session()
    try:
        # Re-analyze all public AOIs (registered user AOIs in Phase 2)
        aois = session.query(AOI).filter_by(is_public=True).limit(50).all()
        log.info("scheduled_reanalysis.start", aoi_count=len(aois))

        dispatched = 0
        orchestrator = AnalysisOrchestrator()
        for aoi in aois:
            try:
                from geoalchemy2.shape import to_shape
                import json
                shape = to_shape(aoi.geom)
                geojson = {"type": "Polygon", "coordinates": list(shape.exterior.coords)}
                end_date = datetime.now(timezone.utc).date().isoformat()
                start_date = (
                    datetime.now(timezone.utc).date() - timedelta(days=30)
                ).isoformat()

                orchestrator.dispatch(
                    aoi_id=str(aoi.id),
                    aoi_geojson=geojson,
                    date_range=(start_date, end_date),
                    triggered_by=triggered_by,
                )
                dispatched += 1
            except Exception as aoi_exc:
                log.warning("scheduled_reanalysis.aoi_failed",
                            aoi_id=str(aoi.id), error=str(aoi_exc))

        log.info("scheduled_reanalysis.complete", dispatched=dispatched)
        return {"dispatched": dispatched}
    finally:
        session.close()


@celery_app.task(name="workers.tasks.alert_tasks.cleanup_expired_tiles",
                 queue="alert_tasks")
def cleanup_expired_tiles() -> dict:
    """
    Remove GEE tile URLs that have expired (> 6h old).
    Updates theme_results rows to clear tile_url.
    """
    from models.theme_result import ThemeResult as ThemeResultModel

    session = _get_sync_session()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
        expired = (
            session.query(ThemeResultModel)
            .filter(ThemeResultModel.tile_url_expires_at < cutoff)
            .filter(ThemeResultModel.tile_url.isnot(None))
            .all()
        )
        count = 0
        for r in expired:
            r.tile_url = None
            count += 1
        session.commit()
        log.info("cleanup_expired_tiles.done", cleared=count)
        return {"cleared": count}
    finally:
        session.close()
