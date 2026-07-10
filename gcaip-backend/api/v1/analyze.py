"""
Analysis endpoints — trigger analysis and stream results via SSE.

POST /analyze      → dispatches Celery tasks, returns job_id + sse_url
GET  /analyze/{id}/status  → polling fallback
GET  /analyze/{id}/stream  → SSE stream (primary consumption method)
GET  /analyze/{id}/results → full results after completion
"""
import asyncio
import json
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from config import settings
from models.analysis_run import AnalysisRun
from models.aoi import AOI
from models.risk_score import RiskScore
from models.theme_result import ThemeResult
from schemas.analysis import (
    AnalyzeRequest,
    AnalyzeResponse,
    FullResultsResponse,
    RiskScoreSchema,
    RunStatusResponse,
    ThemeResultSchema,
)
from services.orchestrator import AnalysisOrchestrator

router = APIRouter()
_orchestrator = AnalysisOrchestrator()


@router.post("/analyze", response_model=AnalyzeResponse, status_code=202)
async def trigger_analysis(
    body: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
) -> AnalyzeResponse:
    """
    Dispatch a full 7-theme analysis for an AOI.
    Returns immediately with a job_id — results stream via SSE.
    """
    # Verify AOI exists
    result = await db.execute(select(AOI).where(AOI.id == body.aoi_id))
    aoi = result.scalar_one_or_none()
    if not aoi:
        raise HTTPException(404, f"AOI {body.aoi_id} not found")

    # Extract AOI GeoJSON
    aoi_geojson = mapping(to_shape(aoi.geom))

    start_date, end_date = body.get_date_range()
    themes = body.get_themes()

    run_id = await _orchestrator.dispatch_async(
        db=db,
        aoi_id=str(body.aoi_id),
        aoi_geojson=dict(aoi_geojson),
        date_range=(start_date, end_date),
        themes=themes,
        triggered_by="user",
    )

    return AnalyzeResponse(
        job_id=uuid.UUID(run_id),
        aoi_id=body.aoi_id,
        status="running",
        sse_url=f"{settings.API_V1_PREFIX}/analyze/{run_id}/stream",
        estimated_seconds=90,
    )


@router.get("/analyze/{run_id}/status", response_model=RunStatusResponse)
async def get_run_status(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RunStatusResponse:
    """Polling fallback — prefer the SSE stream endpoint."""
    result = await db.execute(
        select(AnalysisRun).where(AnalysisRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, f"Analysis run {run_id} not found")

    themes_result = await db.execute(
        select(ThemeResult).where(ThemeResult.run_id == run_id)
    )
    theme_rows = themes_result.scalars().all()

    complete_statuses = {"complete", "failed", "skipped"}
    themes_complete = sum(1 for t in theme_rows if t.status in complete_statuses)
    theme_statuses = {t.theme: t.status for t in theme_rows}

    return RunStatusResponse(
        run_id=run.id,
        status=run.status,
        themes_complete=themes_complete,
        themes_total=len(theme_rows) or 7,
        theme_statuses=theme_statuses,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@router.get("/analyze/{run_id}/stream")
async def stream_results(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    SSE endpoint — streams theme results as they complete via Redis pub/sub.
    Frontend opens EventSource to this URL immediately after POST /analyze.

    On connect, any already-completed results (e.g., from eager task execution
    or if the client reconnects) are emitted immediately before entering the
    pub/sub listen loop.

    Event types:
      theme_complete  → individual theme result ready
      theme_error     → individual theme failed
      risk_score      → composite score computed (all themes done)
      analysis_complete → run finished
      error           → fatal error
    """
    channel = f"gcaip:sse:{run_id}"

    async def event_generator():
        import structlog as _log
        log = _log.get_logger(__name__)

        # Send connection acknowledgement
        yield f"data: {json.dumps({'event': 'connected', 'run_id': str(run_id)})}\n\n"

        # ── P1b fix: subscribe FIRST, then read DB ──────────────────────────────
        # If we did the DB fetch first, any theme_complete events published between
        # the DB read and the subscribe call would be permanently lost (pub/sub has
        # no delivery guarantee for late subscribers). By subscribing first, any
        # messages published during the subsequent DB read are buffered in the
        # subscription queue and will be delivered in the loop below — duplicates
        # are harmless and are deduplicated by the `already_sent` set.
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)

        # Track which themes we've already sent to avoid double-sending
        already_sent: set[str] = set()

        complete_statuses = {"complete", "failed", "skipped"}

        # Pre-fetch any already-completed results from DB (critical for eager mode
        # where tasks complete synchronously before this endpoint is called, and
        # for clients reconnecting after the run has partially or fully completed).
        existing_results = await db.execute(
            select(ThemeResult).where(ThemeResult.run_id == run_id)
        )
        existing_rows = existing_results.scalars().all()

        completed_themes = {
            r.theme for r in existing_rows if r.status in complete_statuses
        }
        total_themes = len(existing_rows)

        # Emit already-completed results from DB
        for row in existing_rows:
            if row.status in complete_statuses:
                event_type = "theme_error" if row.status == "failed" else "theme_complete"
                result_dict = {
                    "result_id": str(row.id),
                    "theme": row.theme,
                    "status": row.status,
                    "tile_url": row.tile_url,
                    "tile_url_expires_at": row.tile_url_expires_at.isoformat() if row.tile_url_expires_at else None,
                    "vis_params": row.vis_params,
                    "metric_value": row.metric_value,
                    "metric_unit": row.metric_unit,
                    "metric_label": row.metric_label,
                    "stats": row.stats or {},
                    "enrichment": row.enrichment or {},
                    "anomaly_score": row.anomaly_score,
                    "confidence": row.confidence,
                    "data_age_hours": row.data_age_hours,
                    "data_source": row.data_source,
                    "error_message": row.error_message,
                    "error_class": row.error_class,
                }
                payload = json.dumps({
                    "event": event_type,
                    "theme": row.theme,
                    "result": result_dict,
                }, default=str)
                yield f"data: {payload}\n\n"
                already_sent.add(row.theme)

        # If all themes are already done, emit analysis_complete and close
        if total_themes > 0 and len(completed_themes) >= total_themes:
            # Also check for risk score
            risk_result = await db.execute(
                select(RiskScore).where(RiskScore.run_id == run_id)
            )
            risk_score = risk_result.scalar_one_or_none()
            if risk_score:
                yield f"data: {json.dumps({'event': 'risk_score', 'score': _serialize_risk_score(risk_score)}, default=str)}\n\n"

            yield f"data: {json.dumps({'event': 'analysis_complete', 'run_id': str(run_id)})}\n\n"
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            await r.aclose()
            return

        # Not all done yet — listen to pub/sub for remaining results
        timeout = 660  # slightly above Celery soft limit (600s) to catch all events
        elapsed = 0.0
        poll_interval = 0.5
        last_keepalive = 0.0
        last_db_check = 0.0
        DB_RECHECK_INTERVAL = 15.0  # Safety net: re-query DB every 15s

        try:
            while elapsed < timeout:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=poll_interval
                )
                if message and message["type"] == "message":
                    data_str = message["data"]

                    # Deduplicate: skip if already sent from DB prefetch
                    try:
                        payload = json.loads(data_str)
                        msg_theme = payload.get("theme")
                        if msg_theme and msg_theme in already_sent:
                            # Already sent from DB prefetch; skip to avoid duplicate
                            pass
                        else:
                            yield f"data: {data_str}\n\n"
                            if msg_theme:
                                already_sent.add(msg_theme)
                            # Close stream after analysis_complete or error
                            if payload.get("event") in ("analysis_complete", "error"):
                                break
                    except json.JSONDecodeError:
                        yield f"data: {data_str}\n\n"

                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                # Keepalive every 15s
                if elapsed - last_keepalive >= 15.0:
                    yield ": keepalive\n\n"
                    last_keepalive = elapsed

                # Safety-net DB re-check every 15s: catch any results that were
                # published to Redis BEFORE our subscription (pub/sub events lost
                # in the subscribe→DB-fetch gap are caught here on first re-check).
                if elapsed - last_db_check >= DB_RECHECK_INTERVAL:
                    last_db_check = elapsed
                    try:
                        recheck = await db.execute(
                            select(ThemeResult).where(ThemeResult.run_id == run_id)
                        )
                        recheck_rows = recheck.scalars().all()
                        for row in recheck_rows:
                            if row.theme not in already_sent and row.status in complete_statuses:
                                event_type = "theme_error" if row.status == "failed" else "theme_complete"
                                result_dict = {
                                    "result_id": str(row.id),
                                    "theme": row.theme,
                                    "status": row.status,
                                    "tile_url": row.tile_url,
                                    "tile_url_expires_at": row.tile_url_expires_at.isoformat() if row.tile_url_expires_at else None,
                                    "vis_params": row.vis_params,
                                    "metric_value": row.metric_value,
                                    "metric_unit": row.metric_unit,
                                    "metric_label": row.metric_label,
                                    "stats": row.stats or {},
                                    "enrichment": row.enrichment or {},
                                    "anomaly_score": row.anomaly_score,
                                    "confidence": row.confidence,
                                    "data_age_hours": row.data_age_hours,
                                    "data_source": row.data_source,
                                    "error_message": row.error_message,
                                    "error_class": row.error_class,
                                }
                                payload_str = json.dumps({
                                    "event": event_type,
                                    "theme": row.theme,
                                    "result": result_dict,
                                }, default=str)
                                yield f"data: {payload_str}\n\n"
                                already_sent.add(row.theme)
                                log.info("sse.db_recheck_recovered", theme=row.theme, run_id=str(run_id))

                        # Check if all themes are now done
                        done_count = sum(1 for row in recheck_rows if row.status in complete_statuses)
                        if recheck_rows and done_count >= len(recheck_rows):
                            # All done — check for risk score and emit complete
                            risk_recheck = await db.execute(
                                select(RiskScore).where(RiskScore.run_id == run_id)
                            )
                            risk_score = risk_recheck.scalar_one_or_none()
                            if risk_score and "risk_score" not in already_sent:
                                yield f"data: {json.dumps({'event': 'risk_score', 'score': _serialize_risk_score(risk_score)}, default=str)}\n\n"
                                already_sent.add("risk_score")
                                yield f"data: {json.dumps({'event': 'analysis_complete', 'run_id': str(run_id)})}\n\n"
                                break
                    except Exception as recheck_exc:
                        log.warning("sse.db_recheck_error", error=str(recheck_exc))

        except asyncio.CancelledError:
            pass  # Client disconnected — clean up
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            await r.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Connection": "keep-alive",
        },
    )


def _serialize_risk_score(risk_score) -> dict:
    """Helper to serialize a RiskScore ORM object for SSE."""
    return {
        "overall_score": risk_score.overall_score,
        "overall_label": risk_score.overall_label,
        "flood_risk": risk_score.flood_risk,
        "erosion_risk": risk_score.erosion_risk,
        "water_stress": risk_score.water_stress,
        "vegetation_health": risk_score.vegetation_health,
        "landuse_pressure": risk_score.landuse_pressure,
        "cross_insights": risk_score.cross_insights or [],
        "population_in_aoi": risk_score.population_in_aoi,
        "population_at_risk": risk_score.population_at_risk,
        "scored_at": risk_score.scored_at.isoformat() if risk_score.scored_at else None,
    }


@router.get("/analyze/{run_id}/results", response_model=FullResultsResponse)
async def get_full_results(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FullResultsResponse:
    """Retrieve complete analysis results after the run finishes."""
    result = await db.execute(
        select(AnalysisRun).where(AnalysisRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, f"Analysis run {run_id} not found")

    themes_result = await db.execute(
        select(ThemeResult).where(ThemeResult.run_id == run_id)
    )
    theme_rows = themes_result.scalars().all()

    risk_result = await db.execute(
        select(RiskScore).where(RiskScore.run_id == run_id)
    )
    risk_score = risk_result.scalar_one_or_none()

    themes_dict = {}
    for t in theme_rows:
        schema = ThemeResultSchema.model_validate(t)
        schema.result_id = t.id
        themes_dict[t.theme] = schema
    cross_insights = risk_score.cross_insights if risk_score else []

    return FullResultsResponse(
        run_id=run.id,
        aoi_id=run.aoi_id,
        status=run.status,
        risk_score=RiskScoreSchema.model_validate(risk_score) if risk_score else None,
        themes=themes_dict,
        cross_insights=cross_insights,
        date_range_start=run.date_range_start,
        date_range_end=run.date_range_end,
        completed_at=run.completed_at,
    )
