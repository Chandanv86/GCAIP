"""
Analysis Orchestrator — creates a run record and dispatches all GEE theme tasks.
This is the entry point called by the /analyze API endpoint.

STEP 1 CHANGE (diagnostic report, Section 4, steps 1-3):
  - AOIClassifier is called BEFORE ThemeResult rows are created.
  - Skipped themes get a pre-written ThemeResult (status="skipped",
    error_class="not_applicable") rather than a dispatched Celery task.
  - If ALL requested themes are skipped, compute_risk_score_task is
    triggered directly so the run never gets stuck at status="running".
  - Both async and sync paths are handled.
"""
import hashlib
import json
import structlog
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from models.analysis_run import AnalysisRun
from models.aoi import AOI
from config import settings

log = structlog.get_logger(__name__)

ALL_THEMES = [
    "rainfall", "landuse",
    "effluent_plume", "coastal_outfall", "pipeline_corridor",
]


class AnalysisOrchestrator:
    """
    Creates AnalysisRun, pre-creates ThemeResult stubs, dispatches Celery tasks.
    Works in both async (FastAPI) and sync (Celery Beat) contexts.
    """

    async def dispatch_async(
        self,
        db: AsyncSession,
        aoi_id: str,
        aoi_geojson: dict,
        date_range: tuple[str, str] | None = None,
        themes: list[str] | None = None,
        triggered_by: str = "user",
    ) -> str:
        """
        Async entry point — called from FastAPI route handlers.

        Returns:
            run_id: UUID string for the created analysis run
        """
        import asyncio
        start_date, end_date = date_range or self._default_date_range()
        themes = themes or ALL_THEMES

        # ── AOI classification (MUST be in executor — makes blocking GEE/HTTP calls) ──
        from services.aoi_classifier import AOIClassifier
        loop = asyncio.get_event_loop()
        try:
            profile = await loop.run_in_executor(
                None, AOIClassifier().classify, aoi_geojson
            )
            # Annotate aoi_geojson with found pipeline geometry so
            # pipeline_corridor.py's tier-1 OSM path actually fires.
            aoi_geojson = profile.annotate_aoi_geojson(aoi_geojson)
        except Exception as clf_exc:
            # Classifier is best-effort — if it fails, run all themes normally
            # rather than blocking analysis entirely.
            log.warning("orchestrator.classifier_failed", error=str(clf_exc))
            profile = None

        # ── Create run record ────────────────────────────────────────────────
        run = AnalysisRun(
            aoi_id=uuid.UUID(aoi_id),
            status="running",
            triggered_by=triggered_by,
            date_range_start=date.fromisoformat(start_date),
            date_range_end=date.fromisoformat(end_date),
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.flush()  # populate run.id before referencing it as a foreign key

        # ── Pre-create ThemeResult rows (skipped or pending) ────────────────
        from models.theme_result import ThemeResult
        skipped = profile.skipped_themes if profile else {}
        dispatch_themes = []

        for theme_name in themes:
            if theme_name in skipped:
                db.add(ThemeResult(
                    run_id=run.id,
                    theme=theme_name,
                    status="skipped",
                    error_class="not_applicable",
                    error_message=skipped[theme_name],
                    metric_label="Not applicable to this AOI",
                    confidence=0.0,
                    data_age_hours=0.0,
                    completed_at=datetime.now(timezone.utc),
                ))
            else:
                db.add(ThemeResult(run_id=run.id, theme=theme_name, status="pending"))
                dispatch_themes.append(theme_name)

        await db.commit()
        await db.refresh(run)
        run_id = str(run.id)

        # ── Cache key from AOI geometry + date range ─────────────────────────
        cache_key = self._make_cache_key(aoi_geojson, start_date, end_date)

        # ── Dispatch or trigger risk score directly if all themes skipped ────
        if not dispatch_themes:
            # Edge case: every requested theme was classified as not-applicable.
            # _check_run_complete() only runs inside a Celery task, so if no
            # task fires, the run would be stuck at status="running" forever.
            log.info(
                "orchestrator.all_themes_skipped",
                run_id=run_id,
                skipped=list(skipped.keys()),
            )
            from workers.tasks.enrichment_tasks import compute_risk_score_task
            compute_risk_score_task.delay(run_id)
        else:
            from workers.tasks.theme_tasks import dispatch_all_themes
            try:
                dispatch_all_themes(
                    run_id=run_id,
                    aoi_geojson=aoi_geojson,
                    date_range=(start_date, end_date),
                    themes=dispatch_themes,
                    cache_key=cache_key,
                )
            except Exception as broker_exc:
                err_str = str(broker_exc).lower()
                if "connection refused" in err_str or "111" in err_str or "redis" in err_str:
                    from sqlalchemy import update
                    from models.analysis_run import AnalysisRun as _Run
                    await db.execute(
                        update(_Run)
                        .where(_Run.id == run.id)
                        .values(status="failed")
                    )
                    await db.commit()
                    from fastapi import HTTPException
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            "Redis task broker is unreachable. "
                            "The analysis job queue cannot start. "
                            f"Configured broker: {settings.CELERY_BROKER_URL}. "
                            "For Docker Compose deployments: verify CELERY_BROKER_URL uses "
                            "the service name 'redis' (not 'localhost'). "
                            "For bare-metal dev: run 'docker compose up -d redis' in gcaip-backend/."
                        ),
                    )
                raise  # non-broker error — let the global handler deal with it

        log.info(
            "orchestrator.dispatched",
            run_id=run_id,
            dispatched=dispatch_themes,
            skipped=list(skipped.keys()),
            date_range=(start_date, end_date),
        )
        return run_id

    def dispatch(
        self,
        aoi_id: str,
        aoi_geojson: dict,
        date_range: tuple[str, str] | None = None,
        themes: list[str] | None = None,
        triggered_by: str = "schedule",
    ) -> str:
        """Sync entry point — called from Celery Beat scheduled tasks."""
        start_date, end_date = date_range or self._default_date_range()
        themes = themes or ALL_THEMES

        # ── AOI classification (no executor needed — already in a worker process) ──
        from services.aoi_classifier import AOIClassifier
        try:
            profile = AOIClassifier().classify(aoi_geojson)
            aoi_geojson = profile.annotate_aoi_geojson(aoi_geojson)
        except Exception as clf_exc:
            log.warning("orchestrator.classifier_failed", error=str(clf_exc))
            profile = None

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        sync_url = settings.DATABASE_URL.replace(
            "postgresql+asyncpg://", "postgresql+psycopg2://"
        )
        engine = create_engine(sync_url, pool_pre_ping=True)
        Session = sessionmaker(bind=engine)
        session = Session()

        skipped = profile.skipped_themes if profile else {}
        dispatch_themes = []

        try:
            run = AnalysisRun(
                aoi_id=uuid.UUID(aoi_id),
                status="running",
                triggered_by=triggered_by,
                date_range_start=date.fromisoformat(start_date),
                date_range_end=date.fromisoformat(end_date),
                started_at=datetime.now(timezone.utc),
            )
            session.add(run)
            session.flush()

            from models.theme_result import ThemeResult
            for theme_name in themes:
                if theme_name in skipped:
                    session.add(ThemeResult(
                        run_id=run.id,
                        theme=theme_name,
                        status="skipped",
                        error_class="not_applicable",
                        error_message=skipped[theme_name],
                        metric_label="Not applicable to this AOI",
                        confidence=0.0,
                        data_age_hours=0.0,
                        completed_at=datetime.now(timezone.utc),
                    ))
                else:
                    session.add(ThemeResult(
                        run_id=run.id, theme=theme_name, status="pending"
                    ))
                    dispatch_themes.append(theme_name)

            session.commit()
            run_id = str(run.id)
        finally:
            session.close()

        cache_key = self._make_cache_key(aoi_geojson, start_date, end_date)

        if not dispatch_themes:
            log.info(
                "orchestrator.all_themes_skipped",
                run_id=run_id,
                skipped=list(skipped.keys()),
            )
            from workers.tasks.enrichment_tasks import compute_risk_score_task
            compute_risk_score_task.delay(run_id)
        else:
            from workers.tasks.theme_tasks import dispatch_all_themes
            dispatch_all_themes(
                run_id=run_id,
                aoi_geojson=aoi_geojson,
                date_range=(start_date, end_date),
                themes=dispatch_themes,
                cache_key=cache_key,
            )
        return run_id

    @staticmethod
    def _default_date_range() -> tuple[str, str]:
        """Default: last 30 days ending today."""
        end = date.today()
        start = end - timedelta(days=30)
        return start.isoformat(), end.isoformat()

    @staticmethod
    def _make_cache_key(aoi_geojson: dict, start: str, end: str) -> str:
        """
        Deterministic cache key for an AOI + date range.
        Same geometry within 6h returns cached GEE results (saves quota).
        """
        payload = json.dumps(aoi_geojson, sort_keys=True) + start + end
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
