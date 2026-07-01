"""
Celery tasks — one per GEE theme processor.
All tasks run in the `gee_tasks` queue (dedicated worker pool).

Each task:
  1. Runs the GEE processor
  2. Stores ThemeResult in DB
  3. Publishes result to Redis pub/sub (SSE consumers subscribe)
  4. Triggers enrichment task
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from celery import Task, chord, group
from sqlalchemy import select, update

from workers.celery_app import celery_app

import structlog
log = structlog.get_logger(__name__)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_sync_session():
    """Synchronous SQLAlchemy session for Celery tasks (not async)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from config import settings

    # Convert asyncpg URL to psycopg2 for sync Celery workers
    sync_url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    )
    engine = create_engine(sync_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    return Session()


def _get_redis():
    """Redis client for pub/sub SSE notifications."""
    import redis as redis_lib
    from config import settings
    return redis_lib.from_url(settings.REDIS_URL)


def _publish_theme_event(run_id: str, theme: str, result_dict: dict) -> None:
    """Publish theme result to Redis channel so SSE endpoint can stream it."""
    r = _get_redis()
    channel = f"gcaip:sse:{run_id}"
    payload = json.dumps({
        "event": "theme_complete" if not result_dict.get("error") else "theme_error",
        "theme": theme,
        "result": result_dict,
    }, default=str)
    r.publish(channel, payload)
    r.expire(channel, 3600)  # Channel auto-expires after 1h


def _store_theme_result(run_id: str, theme: str, result) -> None:
    """Persist ThemeResult to the theme_results table."""
    from models.theme_result import ThemeResult as ThemeResultModel

    session = _get_sync_session()
    try:
        obj = (
            session.query(ThemeResultModel)
            .filter_by(run_id=run_id, theme=theme)
            .first()
        )
        now = datetime.now(timezone.utc)
        if obj is None:
            obj = ThemeResultModel(
                run_id=run_id,
                theme=theme,
            )
            session.add(obj)

        obj.status = "failed" if result.error else "complete"
        obj.tile_url = result.tile_url
        obj.tile_url_expires_at = result.tile_url_expires_at
        obj.vis_params = result.vis_params
        obj.metric_value = result.metric_value
        obj.metric_unit = result.metric_unit
        obj.metric_label = result.metric_label
        obj.stats = result.stats
        obj.anomaly_score = result.anomaly_score
        obj.confidence = result.confidence
        obj.data_age_hours = result.data_age_hours
        obj.data_source = result.data_source
        obj.error_message = result.error
        obj.completed_at = now

        session.commit()
    except Exception as exc:
        session.rollback()
        log.error("theme_task.store_error", theme=theme, error=str(exc))
        raise
    finally:
        session.close()


def _check_run_complete(run_id: str) -> bool:
    """Check if all 7 theme tasks are done; if so, trigger risk scoring."""
    from models.theme_result import ThemeResult as ThemeResultModel

    session = _get_sync_session()
    try:
        results = (
            session.query(ThemeResultModel)
            .filter_by(run_id=run_id)
            .all()
        )
        done_statuses = {"complete", "failed", "skipped"}
        if all(r.status in done_statuses for r in results) and len(results) >= len(ACTIVE_THEMES):
            # All themes done — trigger risk score computation
            from workers.tasks.enrichment_tasks import compute_risk_score_task
            compute_risk_score_task.delay(run_id)
            return True
        return False
    finally:
        session.close()


# ── Base task class ────────────────────────────────────────────────────────────

class GEETask(Task):
    """Base class: sets status=running on start, status=failed on crash."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        run_id = kwargs.get("run_id") or (args[0] if args else None)
        theme = kwargs.get("theme") or self.name.split(".")[-1].replace("_task", "")
        if run_id:
            log.error(
                "gee_task.failed",
                task=self.name,
                run_id=str(run_id),
                error=str(exc),
            )
            _publish_theme_event(
                str(run_id), theme,
                {"theme": theme, "error": str(exc), "status": "failed"},
            )


# ── Theme tasks ────────────────────────────────────────────────────────────────

def _run_theme(processor_cls, theme: str, run_id: str, aoi_geojson: dict,
               date_range: tuple, cache_key: str | None = None) -> dict:
    """
    Generic theme runner — processor → store → publish → check completion.
    Used by all 7 theme tasks.
    """
    import redis as redis_lib
    from config import settings

    # Cache check — same AOI within 6h skips GEE
    if cache_key:
        r = redis_lib.from_url(settings.REDIS_URL)
        cached = r.get(f"gcaip:cache:{cache_key}:{theme}")
        if cached:
            log.info("theme_task.cache_hit", theme=theme, key=cache_key)
            result_dict = json.loads(cached)
            
            # Reconstruct ThemeResult for DB storage
            from gee.processors.base import ThemeResult
            expires_str = result_dict.get("tile_url_expires_at")
            expires_dt = datetime.fromisoformat(expires_str) if expires_str else None
            
            result = ThemeResult(
                theme=result_dict.get("theme", theme),
                tile_url=result_dict.get("tile_url"),
                tile_url_expires_at=expires_dt,
                vis_params=result_dict.get("vis_params"),
                metric_value=result_dict.get("metric_value"),
                metric_unit=result_dict.get("metric_unit"),
                metric_label=result_dict.get("metric_label"),
                stats=result_dict.get("stats"),
                anomaly_score=result_dict.get("anomaly_score"),
                confidence=result_dict.get("confidence"),
                data_age_hours=result_dict.get("data_age_hours"),
                data_source=result_dict.get("data_source"),
                error=result_dict.get("error"),
            )
            
            _store_theme_result(run_id, theme, result)
            _publish_theme_event(run_id, theme, result_dict)
            _check_run_complete(run_id)
            return result_dict

    processor = processor_cls()
    result = processor.compute(aoi_geojson, date_range)
    result_dict = result.to_dict()

    # Cache the result
    if (cache_key 
        and not result.error 
        and result.confidence is not None 
        and result.confidence >= 0.4  # minimum confidence to cache
        and result.metric_value is not None):
        r = redis_lib.from_url(settings.REDIS_URL)
        r.setex(
            f"gcaip:cache:{cache_key}:{theme}",
            settings.REDIS_TTL_TILE_URL,
            json.dumps(result_dict, default=str),
        )

    _store_theme_result(run_id, theme, result)
    _publish_theme_event(run_id, theme, result_dict)
    _check_run_complete(run_id)
    return result_dict


@celery_app.task(base=GEETask, name="workers.tasks.theme_tasks.flood_task",
                  bind=True, max_retries=2)
def flood_task(self, run_id: str, aoi_geojson: dict,
               date_range: list, cache_key: str | None = None) -> dict:
    """Theme 1: Sentinel-1 SAR flood extent."""
    from gee.processors.flood import FloodProcessor
    return _run_theme(FloodProcessor, "flood", run_id, aoi_geojson,
                      tuple(date_range), cache_key)


@celery_app.task(base=GEETask, name="workers.tasks.theme_tasks.rainfall_task",
                  bind=True, max_retries=2)
def rainfall_task(self, run_id: str, aoi_geojson: dict,
                  date_range: list, cache_key: str | None = None) -> dict:
    """Theme 2: GPM IMERG vs CHIRPS rainfall anomaly."""
    from gee.processors.rainfall import RainfallProcessor
    return _run_theme(RainfallProcessor, "rainfall", run_id, aoi_geojson,
                      tuple(date_range), cache_key)


@celery_app.task(base=GEETask, name="workers.tasks.theme_tasks.reservoir_task",
                  bind=True, max_retries=2)
def reservoir_task(self, run_id: str, aoi_geojson: dict,
                   date_range: list, cache_key: str | None = None) -> dict:
    """Theme 3: Reservoir fill status (JRC + S1)."""
    from gee.processors.reservoir import ReservoirProcessor
    return _run_theme(ReservoirProcessor, "reservoir", run_id, aoi_geojson,
                      tuple(date_range), cache_key)


@celery_app.task(base=GEETask, name="workers.tasks.theme_tasks.mangrove_task",
                  bind=True, max_retries=2)
def mangrove_task(self, run_id: str, aoi_geojson: dict,
                  date_range: list, cache_key: str | None = None) -> dict:
    """Theme 4: GMW v3 + Sentinel-2 MVI mangrove change."""
    from gee.processors.mangrove import MangroveProcessor
    return _run_theme(MangroveProcessor, "mangrove", run_id, aoi_geojson,
                      tuple(date_range), cache_key)


@celery_app.task(base=GEETask, name="workers.tasks.theme_tasks.erosion_task",
                  bind=True, max_retries=2)
def erosion_task(self, run_id: str, aoi_geojson: dict,
                 date_range: list, cache_key: str | None = None) -> dict:
    """Theme 5: Multi-temporal SAR shoreline erosion rate."""
    from gee.processors.erosion import ErosionProcessor
    return _run_theme(ErosionProcessor, "erosion", run_id, aoi_geojson,
                      tuple(date_range), cache_key)


@celery_app.task(base=GEETask, name="workers.tasks.theme_tasks.vegetation_task",
                  bind=True, max_retries=2)
def vegetation_task(self, run_id: str, aoi_geojson: dict,
                    date_range: list, cache_key: str | None = None) -> dict:
    """Theme 6: Sentinel-2 NDVI vegetation buffer analysis."""
    from gee.processors.vegetation import VegetationProcessor
    return _run_theme(VegetationProcessor, "vegetation", run_id, aoi_geojson,
                      tuple(date_range), cache_key)


@celery_app.task(base=GEETask, name="workers.tasks.theme_tasks.landuse_task",
                  bind=True, max_retries=2)
def landuse_task(self, run_id: str, aoi_geojson: dict,
                 date_range: list, cache_key: str | None = None) -> dict:
    """Theme 7: Dynamic World vs ESA WorldCover land use change."""
    from gee.processors.landuse import LandUseProcessor
    return _run_theme(LandUseProcessor, "landuse", run_id, aoi_geojson,
                      tuple(date_range), cache_key)


# ── Orchestration ──────────────────────────────────────────────────────────────

THEME_TASKS = {
    "flood": flood_task,
    "rainfall": rainfall_task,
    "reservoir": reservoir_task,
    "mangrove": mangrove_task,
    "erosion": erosion_task,
    "vegetation": vegetation_task,
    "landuse": landuse_task,
}

# Active themes — only these are dispatched by default
ACTIVE_THEMES = {"rainfall", "landuse"}


def dispatch_all_themes(
    run_id: str,
    aoi_geojson: dict,
    date_range: tuple[str, str],
    themes: list[str] | None = None,
    cache_key: str | None = None,
) -> list:
    """
    Dispatch all (or selected) theme tasks in parallel.
    Each task runs independently — results stream back as they complete.

    Returns list of AsyncResult objects.
    """
    # ThemeResult rows are now pre-created by the caller (dispatch_async or dispatch)
    # inside their own transaction, avoiding sync db session overhead and deadlocks.

    jobs = []
    for theme_name, task_fn in THEME_TASKS.items():
        if themes and theme_name not in themes:
            continue
        job = task_fn.apply_async(
            kwargs={
                "run_id": run_id,
                "aoi_geojson": aoi_geojson,
                "date_range": list(date_range),
                "cache_key": cache_key,
            },
            queue="gee_tasks",
        )
        jobs.append(job)
        log.info("theme_task.dispatched", theme=theme_name, run_id=run_id)

    return jobs
