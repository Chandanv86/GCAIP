"""PDF report generation endpoint — async via Celery."""
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from models.analysis_run import AnalysisRun

router = APIRouter()


@router.post("/reports/{run_id}", status_code=202)
async def request_report(
    run_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Trigger async PDF report generation for a completed analysis run.
    Returns a task ID to poll for completion.
    """
    result = await db.execute(
        select(AnalysisRun).where(AnalysisRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Analysis run not found")
    if run.status != "complete":
        raise HTTPException(400, "Analysis run not yet complete")

    from workers.tasks.report_tasks import generate_report_task
    task = generate_report_task.delay(str(run_id))

    return {
        "task_id": task.id,
        "run_id": str(run_id),
        "status": "pending",
        "poll_url": f"/api/v1/reports/status/{task.id}",
    }


@router.get("/reports/status/{task_id}")
async def report_status(task_id: str) -> dict:
    """Check PDF generation status."""
    from workers.celery_app import celery_app
    result = celery_app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": result.result if result.ready() else None,
    }
