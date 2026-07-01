"""Health check — verifies DB, Redis, and GEE connectivity."""
import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from config import settings

router = APIRouter()


@router.get("/health", summary="System health check")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict:
    checks: dict[str, dict] = {}

    # DB check
    try:
        t0 = time.monotonic()
        await db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000, 1)}
    except Exception as exc:
        checks["database"] = {"status": "error", "error": str(exc)}

    # Redis check
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL)
        t0 = time.monotonic()
        await r.ping()
        checks["redis"] = {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000, 1)}
        await r.aclose()
    except Exception as exc:
        checks["redis"] = {"status": "error", "error": str(exc)}

    # GEE check (non-blocking — just test initialization)
    try:
        from gee.client import test_connection
        checks["gee"] = test_connection()
    except Exception as exc:
        checks["gee"] = {"status": "error", "error": str(exc)}

    overall = "ok" if all(v.get("status") == "ok" for v in checks.values()) else "degraded"
    return {
        "status": overall,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "checks": checks,
    }
