"""
Analysis Orchestrator — creates a run record and dispatches all 7 GEE theme tasks.
This is the entry point called by the /analyze API endpoint.
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

ALL_THEMES = ["rainfall", "landuse"]


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
        start_date, end_date = date_range or self._default_date_range()
        themes = themes or ALL_THEMES

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
        await db.flush()  # Flush to populate run.id before referencing it as a foreign key
        
        # Pre-create pending ThemeResult rows asynchronously
        from models.theme_result import ThemeResult
        for theme_name in themes:
            db.add(ThemeResult(
                run_id=run.id,
                theme=theme_name,
                status="pending",
            ))
            
        await db.commit()
        await db.refresh(run)
        run_id = str(run.id)

        # ── Cache key from AOI geometry + date range ─────────────────────────
        cache_key = self._make_cache_key(aoi_geojson, start_date, end_date)

        # ── Dispatch GEE tasks in parallel ───────────────────────────────────
        from workers.tasks.theme_tasks import dispatch_all_themes
        dispatch_all_themes(
            run_id=run_id,
            aoi_geojson=aoi_geojson,
            date_range=(start_date, end_date),
            themes=themes,
            cache_key=cache_key,
        )

        log.info(
            "orchestrator.dispatched",
            run_id=run_id,
            themes=themes,
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

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        sync_url = settings.DATABASE_URL.replace(
            "postgresql+asyncpg://", "postgresql+psycopg2://"
        )
        engine = create_engine(sync_url, pool_pre_ping=True)
        Session = sessionmaker(bind=engine)
        session = Session()

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
            session.flush()  # Flush to populate run.id before referencing it as a foreign key
            
            # Pre-create pending ThemeResult rows synchronously
            from models.theme_result import ThemeResult
            for theme_name in themes:
                session.add(ThemeResult(
                    run_id=run.id,
                    theme=theme_name,
                    status="pending",
                ))
                
            session.commit()
            run_id = str(run.id)
        finally:
            session.close()

        cache_key = self._make_cache_key(aoi_geojson, start_date, end_date)
        from workers.tasks.theme_tasks import dispatch_all_themes
        dispatch_all_themes(
            run_id=run_id,
            aoi_geojson=aoi_geojson,
            date_range=(start_date, end_date),
            themes=themes,
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
