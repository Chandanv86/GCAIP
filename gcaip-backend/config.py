"""
GCAIP — Application Configuration
All settings sourced from environment variables with safe defaults.
"""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    APP_NAME: str = "GCAIP"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # --- Security ---
    SECRET_KEY: str = "change-me-in-production-use-secrets-manager"
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # --- Database ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://gcaip:gcaip_secret@localhost:5435/gcaip"
    )
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TTL_TILE_URL: int = 21600    # 6h — GEE tile URL expiry
    REDIS_TTL_STATS: int = 21600       # 6h — analysis result cache
    REDIS_TTL_OSM: int = 86400         # 24h — OSM Overpass cache

    # --- Google Earth Engine ---
    GEE_SERVICE_ACCOUNT: str = ""
    GEE_CREDENTIALS_PATH: str = "credentials/gee-service-account.json"
    GEE_PROJECT: str = "earthengine-public"
    GEE_SCALE_DEFAULT: int = 30        # metres, S2 resolution
    GEE_SCALE_S1: int = 10             # metres, Sentinel-1 native
    GEE_TIMEOUT_SECONDS: int = 120
    GEE_MAX_RETRIES: int = 3
    GEE_AOI_MAX_KM2_ANON: float = 500.0
    GEE_AOI_MAX_KM2_USER: float = 2000.0

    # --- Celery ---
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    # GEE worst-case budget per task:
    #   safe_call retries up to GEE_MAX_RETRIES=3 attempts, each up to GEE_TIMEOUT_SECONDS=120s
    #   plus exponential backoff: 1s + 2s + 4s = 7s between retries.
    #   Per safe_call worst case: 120*3 + 7 = 367s.
    #   A typical processor makes ~5-8 sequential safe_call invocations (stats + tile + fallback).
    #   Conservative per-task ceiling: 8 × 367 = ~2936s.  Practically retries are rare;
    #   600s soft / 720s hard covers the real p99 (2-3 sequential calls, rarely retried)
    #   while leaving a clean SIGTERM window between soft and hard limits.
    #   If you raise GEE_TIMEOUT_SECONDS or GEE_MAX_RETRIES, raise these proportionally.
    CELERY_TASK_SOFT_TIME_LIMIT: int = 600   # 10 min — triggers SoftTimeLimitExceeded
    CELERY_TASK_TIME_LIMIT: int = 720        # 12 min — hard SIGKILL after soft+grace
    CELERY_BEAT_SCHEDULE_INTERVAL: int = 3600  # 1h between scheduled runs

    # --- External APIs ---
    WORLDPOP_BASE_URL: str = "https://www.worldpop.org/rest/data"
    OVERPASS_BASE_URL: str = "https://overpass-api.de/api/interpreter"
    NOMINATIM_BASE_URL: str = "https://nominatim.openstreetmap.org"
    GLOFAS_CDS_URL: str = "https://cds.climate.copernicus.eu/api/v2"
    GLOFAS_API_KEY: str = ""
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = "alerts@gcaip.io"

    # --- Feature flags ---
    ENABLE_SCHEDULED_ANALYSIS: bool = True
    ENABLE_EMAIL_ALERTS: bool = False       # Phase 2
    ENABLE_GLOFAS: bool = False             # Phase 2
    ALERT_CONFIDENCE_THRESHOLD: float = 0.6  # Do not alert below this


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton — load once, reuse everywhere."""
    return Settings()


settings = get_settings()
