import sys
import os
# Ensure backend folder is in Python path for Celery worker processes
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from celery import Celery
from celery.schedules import crontab
import structlog

from config import settings
from db.base import import_all_models

# Register all models so SQLAlchemy relationships can resolve in Celery tasks
import_all_models()

celery_app = Celery(
    "gcaip",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "workers.tasks.theme_tasks",
        "workers.tasks.enrichment_tasks",
        "workers.tasks.alert_tasks",
        "workers.tasks.report_tasks",
    ],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Timeouts — GEE calls must not run forever
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,

    # Routing — separate queues for GEE vs enrichment vs alerts
    task_routes={
        "workers.tasks.theme_tasks.*": {"queue": "gee_tasks"},
        "workers.tasks.enrichment_tasks.*": {"queue": "enrichment_tasks"},
        "workers.tasks.alert_tasks.*": {"queue": "alert_tasks"},
        "workers.tasks.report_tasks.*": {"queue": "default"},
    },

    # Retry policy defaults
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # One task at a time per worker (GEE is CPU-light but I/O-heavy)

    # Result expiry — keep results for 24h
    result_expires=86400,

    # Beat schedule — Phase 2 scheduled re-analysis
    beat_schedule={
        "scheduled-reanalysis": {
            "task": "workers.tasks.alert_tasks.scheduled_reanalysis",
            "schedule": crontab(minute=0, hour="*/6"),  # Every 6 hours
            "kwargs": {"triggered_by": "schedule"},
        },
        "cleanup-expired-tiles": {
            "task": "workers.tasks.alert_tasks.cleanup_expired_tiles",
            "schedule": crontab(minute=30, hour="*/6"),
        },
    },
)


@celery_app.on_after_finalize.connect
def setup_gee(sender, **kwargs):
    """Initialize GEE once per worker process after Celery starts."""
    try:
        from gee import client as gee_client
        gee_client.initialize()
    except Exception as exc:
        log = structlog.get_logger(__name__)
        log.error(
            "celery.gee_init_failed", error=str(exc)
        )
