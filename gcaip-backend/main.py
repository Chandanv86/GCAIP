"""
GCAIP — FastAPI Application Entry Point
Registers all routers, middleware, and startup events.
"""
import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from config import settings
from db.session import engine
from db.base import Base, import_all_models
from api.v1 import aoi, analyze, themes, alerts, reports, timeseries, health

import_all_models()  # Register all ORM models on Base.metadata

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    log.info("gcaip.startup", version=settings.APP_VERSION, env=settings.ENVIRONMENT)
    # DB tables are managed by Alembic — do not auto-create here in production.
    # In dev/test, you may uncomment the line below:
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.create_all)
    yield
    log.info("gcaip.shutdown")
    await engine.dispose()


app = FastAPI(
    title="GCAIP — Geospatial Climate Adaptation Intelligence Platform",
    version=settings.APP_VERSION,
    description=(
        "Converts free satellite data into actionable climate intelligence. "
        "Every result includes: what is happening, how bad, who is affected, what to do."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# --- Routers ---
PREFIX = settings.API_V1_PREFIX

app.include_router(health.router, prefix=PREFIX, tags=["Health"])
app.include_router(aoi.router, prefix=PREFIX, tags=["AOI"])
app.include_router(analyze.router, prefix=PREFIX, tags=["Analysis"])
app.include_router(themes.router, prefix=PREFIX, tags=["Themes"])
app.include_router(alerts.router, prefix=PREFIX, tags=["Alerts"])
app.include_router(reports.router, prefix=PREFIX, tags=["Reports"])
app.include_router(timeseries.router, prefix=PREFIX, tags=["Time Series"])


@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    import traceback
    log.error("gcaip.unhandled_exception", exc=str(exc), path=str(request.url))
    if settings.DEBUG:
        tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "traceback": tb,
            },
        )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Our team has been notified."},
    )


@app.get("/", include_in_schema=False)
async def root():
    return {
        "name": "GCAIP API",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": f"{PREFIX}/health",
    }
