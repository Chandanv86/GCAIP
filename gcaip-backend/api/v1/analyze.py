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
async def stream_results(run_id: uuid.UUID) -> StreamingResponse:
    """
    SSE endpoint — streams theme results as they complete via Redis pub/sub.
    Frontend opens EventSource to this URL immediately after POST /analyze.

    Event types:
      theme_complete  → individual theme result ready
      theme_error     → individual theme failed
      risk_score      → composite score computed (all themes done)
      analysis_complete → run finished
      error           → fatal error
    """
    channel = f"gcaip:sse:{run_id}"

    async def event_generator():
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)

        # Send connection acknowledgement
        yield f"data: {json.dumps({'event': 'connected', 'run_id': str(run_id)})}\n\n"

        timeout = 180  # 3 minutes max stream
        elapsed = 0
        poll_interval = 0.5

        try:
            while elapsed < timeout:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=poll_interval
                )
                if message and message["type"] == "message":
                    data_str = message["data"]
                    yield f"data: {data_str}\n\n"

                    # Close stream after analysis_complete or error
                    try:
                        payload = json.loads(data_str)
                        if payload.get("event") in ("analysis_complete", "error"):
                            break
                    except json.JSONDecodeError:
                        pass

                # Send keepalive comment every 15s
                elif elapsed % 15 == 0:
                    yield ": keepalive\n\n"

                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
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

    themes_dict = {t.theme: ThemeResultSchema.model_validate(t) for t in theme_rows}
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
