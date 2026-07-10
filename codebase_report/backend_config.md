# Backend Config, Entry Point, & DB Models

This section covers the configuration parser, API entry point, database sessions, and the ORM models.

---

## 1. Configuration & Entry Point

### `config.py`
*   **One-line purpose**: All system settings sourced from environment variables with safe defaults.
*   **Type**: Configuration Module (Pydantic BaseSettings).
*   **Definitions**:
    *   `class Settings(BaseSettings)`: Main settings class.
        *   `model_config`: Config dict specifying `.env` search, utf-8, case insensitive, extra variables ignored.
    *   `get_settings() -> Settings`: Singleton accessor wrapped in `@lru_cache(maxsize=1)`.
*   **Exact Constants, Defaults & Keys**:
    *   `APP_NAME` = `"GCAIP"`
    *   `APP_VERSION` = `"1.0.0"`
    *   `ENVIRONMENT` = `"development"` (Literal: development\|staging\|production)
    *   `DEBUG` = `False`
    *   `API_V1_PREFIX` = `"/api/v1"`
    *   `SECRET_KEY` = `"change-me-in-production-use-secrets-manager"`
    *   `CORS_ORIGINS` = `["http://localhost:5173", "http://localhost:3000"]`
    *   `DATABASE_URL` = `"postgresql+asyncpg://gcaip:gcaip_secret@localhost:5435/gcaip"`
    *   `DB_POOL_SIZE` = `10`
    *   `DB_MAX_OVERFLOW` = `20`
    *   `DB_ECHO` = `False`
    *   `REDIS_URL` = `"redis://localhost:6379/0"`
    *   `REDIS_TTL_TILE_URL` = `21600` (6 hours)
    *   `REDIS_TTL_STATS` = `21600` (6 hours)
    *   `REDIS_TTL_OSM` = `86400` (24 hours)
    *   `GEE_SERVICE_ACCOUNT` = `""`
    *   `GEE_CREDENTIALS_PATH` = `"credentials/gee-service-account.json"`
    *   `GEE_PROJECT` = `"earthengine-public"`
    *   `GEE_SCALE_DEFAULT` = `30` (meters, S2 bands resolution)
    *   `GEE_SCALE_S1` = `10` (meters, Sentinel-1 resolution)
    *   `GEE_TIMEOUT_SECONDS` = `120`
    *   `GEE_MAX_RETRIES` = `3`
    *   `GEE_AOI_MAX_KM2_ANON` = `500.0`
    *   `GEE_AOI_MAX_KM2_USER` = `2000.0`
    *   `CELERY_BROKER_URL` = `"redis://localhost:6379/0"`
    *   `CELERY_RESULT_BACKEND` = `"redis://localhost:6379/1"`
    *   `CELERY_TASK_SOFT_TIME_LIMIT` = `180` (3 minutes)
    *   `CELERY_TASK_TIME_LIMIT` = `240` (4 minutes)
    *   `CELERY_BEAT_SCHEDULE_INTERVAL` = `3600` (1 hour)
    *   `WORLDPOP_BASE_URL` = `"https://www.worldpop.org/rest/data"`
    *   `OVERPASS_BASE_URL` = `"https://overpass-api.de/api/interpreter"`
    *   `NOMINATIM_BASE_URL` = `"https://nominatim.openstreetmap.org"`
    *   `GLOFAS_CDS_URL` = `"https://cds.climate.copernicus.eu/api/v2"`
    *   `GLOFAS_API_KEY` = `""`
    *   `SENDGRID_API_KEY` = `""`
    *   `SENDGRID_FROM_EMAIL` = `"alerts@gcaip.io"`
    *   `ENABLE_SCHEDULED_ANALYSIS` = `True`
    *   `ENABLE_EMAIL_ALERTS` = `False`
    *   `ENABLE_GLOFAS` = `False`
    *   `ALERT_CONFIDENCE_THRESHOLD` = `0.6`

---

### `main.py`
*   **One-line purpose**: FastAPI application bootstrap registering routers, middleware, and startup/shutdown lifecycles.
*   **Type**: App Controller / Router Registry.
*   **Dependencies**: Imports `structlog`, `fastapi`, `config`, `db.session`, `db.base`, and all API v1 endpoints.
*   **Logic Flow**:
    1.  Calls `import_all_models()` to register all ORM definitions on the SQLAlchemy base.
    2.  Creates `lifespan(app: FastAPI)` context manager to log startup info and dispose of the async `engine` pool on shutdown.
    3.  Instantiates `FastAPI` with CORS and Gzip middleware (triggers on responses > 1000 bytes).
    4.  Registers routers: `health`, `aoi`, `analyze`, `themes`, `alerts`, `reports`, `timeseries` with prefix `/api/v1`.
    5.  Implements `@app.exception_handler(Exception)` global error handler. If `settings.DEBUG` is active, it returns the exception string and formatting traceback (HTTP 500). Otherwise, it hides details behind `"Internal server error. Our team has been notified."`.
    6.  Registers simple root path `/` returning basic schema pointers.

---

## 2. Database Session & Base

### `db/session.py`
*   **One-line purpose**: Setup engine connection pools and session factory for async SQL interaction.
*   **Type**: Connection Factory.
*   **Functions**:
    *   `async def get_db() -> AsyncGenerator[AsyncSession, None]`: FastAPI dependency. Yields `AsyncSessionLocal()`. Commits session modifications on success, executes `await session.rollback()` on exceptions, and closes session on cleanup.
*   **Exact Constants & Defaults**:
    *   `pool_size` = `settings.DB_POOL_SIZE` (`10`)
    *   `max_overflow` = `settings.DB_MAX_OVERFLOW` (`20`)
    *   `echo` = `settings.DB_ECHO` (`False`)
    *   `json_serializer` = custom lambda using standard `json.dumps(obj, default=str)` to support native PostgreSQL JSONB columns.
    *   `expire_on_commit` = `False`, `autoflush` = `False`, `autocommit` = `False`.

### `db/base.py`
*   **One-line purpose**: Declarative base structure class for model migrations.
*   **Type**: Declarative Base.
*   **Functions**:
    *   `import_all_models() -> None`: Imports all database models (`User`, `AOI`, `AnalysisRun`, `ThemeResult`, `RiskScore`, `Alert`) to register them against `Base.metadata`. Avoids circular imports by importing within the function body.

---

## 3. Database ORM Models

### `models/user.py`
*   **One-line purpose**: User records containing credentials, usage tiers, and notification settings.
*   **Type**: ORM model.
*   **Schema**:
    *   `id` (`UUID`): Primary key, default `uuid.uuid4`.
    *   `email` (`String(255)`): Unique, indexed, not nullable.
    *   `display_name` (`String(255)`): Nullable.
    *   `hashed_password` (`String(255)`): Nullable.
    *   `is_verified` (`Boolean`): Default `False`.
    *   `is_active` (`Boolean`): Default `True`.
    *   `tier` (`String(32)`): Default `"free"` (free\|pro\|org).
    *   `max_aoi_km2` (`Float`): Default `500.0`.
    *   `monthly_analysis_count` (`Integer`): Default `0`.
    *   `preferred_notification_email` (`String(255)`): Nullable.
    *   `timezone` (`String(64)`): Default `"UTC"`.
    *   `created_at` (`DateTime(timezone=True)`): Defaults to server time.
    *   `last_login_at` (`DateTime(timezone=True)`): Nullable.
*   **Relationships**: `aois` maps one-to-many to `AOI` via `relationship("AOI", back_populates="creator")`.

### `models/aoi.py`
*   **One-line purpose**: Boundary boundaries (polygons) drawn by users and admin details.
*   **Type**: ORM model.
*   **Schema**:
    *   `id` (`UUID`): Primary key.
    *   `name` (`String(512)`): Boundary name.
    *   `geom` (`Geometry(geometry_type="POLYGON", srid=4326)`): Boundary coordinates. GIST Index `idx_aois_geom`.
    *   `bbox` (`Geometry(geometry_type="POLYGON", srid=4326)`): Boundary bounding box envelope.
    *   `area_km2` (`Float`): Boundary surface area in square kilometers.
    *   `country_code` (`String(2)`): Country code from geocoder.
    *   `admin_level1` (`String(256)`): Province/State.
    *   `admin_level2` (`String(256)`): District/County.
    *   `created_by` (`UUID`): Foreign key to `users.id`, Index `idx_aois_user`.
    *   `is_public` (`Boolean`): Default `False`.
    *   `tags` (`JSONB`): Key-value markers, default `dict`.
    *   `created_at` (`DateTime(timezone=True)`): Defaults to server time.
*   **Relationships**:
    *   `creator`: Back-populates to `User`.
    *   `analysis_runs`: Back-populates to `AnalysisRun`.
    *   `alerts`: Back-populates to `Alert`.

### `models/analysis_run.py`
*   **One-line purpose**: State tracker for multi-theme parallel analysis pipelines.
*   **Type**: ORM model.
*   **Schema**:
    *   `id` (`UUID`): Primary key.
    *   `aoi_id` (`UUID`): Foreign key to `aois.id`, Index `idx_runs_aoi_time` (compound with `created_at`).
    *   `status` (`String(32)`): pending\|running\|complete\|failed. Index `idx_runs_status`.
    *   `triggered_by` (`String(32)`): user\|schedule\|alert.
    *   `date_range_start` (`Date`): Not nullable.
    *   `date_range_end` (`Date`): Not nullable.
    *   `celery_task_id` (`String(255)`): Dispatch task ID.
    *   `started_at` (`DateTime(timezone=True)`): Start timestamp.
    *   `completed_at` (`DateTime(timezone=True)`): End timestamp.
    *   `duration_sec` (`Float`): Compute latency.
    *   `error_message` (`Text`): Stack trace if failed.
    *   `gee_quota_used` (`Float`): Compute usage credits tracker.
    *   `created_at` (`DateTime(timezone=True)`): Default server timestamp.
*   **Relationships**:
    *   `aoi`: Back-populates to `AOI`.
    *   `theme_results`: Back-populates to `ThemeResult`.
    *   `risk_score`: Back-populates to `RiskScore` (one-to-one).

### `models/theme_result.py`
*   **One-line purpose**: Individual Google Earth Engine theme execution result data.
*   **Type**: ORM model.
*   **Schema**:
    *   `id` (`UUID`): Primary key.
    *   `run_id` (`UUID`): Foreign key to `analysis_runs.id`. Index `idx_results_run`.
    *   `theme` (`String(64)`): Theme code (e.g. flood\|landuse\|effluent_plume). Compound Index `idx_results_theme_time` with `completed_at`.
    *   `status` (`String(32)`): pending\|running\|complete\|failed\|skipped.
    *   `tile_url` (`Text`): XYZ map tiles template.
    *   `tile_url_expires_at` (`DateTime(timezone=True)`): URL validity limit.
    *   `vis_params` (`JSONB`): Map styling constraints.
    *   `metric_value` (`Float`): Main calculated metric.
    *   `metric_unit` (`String(32)`): Metric units.
    *   `metric_label` (`String(512)`): Readable summary.
    *   `stats` (`JSONB`): Raw zonal statistical aggregates, default `dict`.
    *   `enrichment` (`JSONB`): WorldPop/OSM population and infrastructure, default `dict`.
    *   `anomaly_score` (`Float`): Computed relative change indicator (0-100).
    *   `confidence` (`Float`): Compute precision score (0-1).
    *   `data_age_hours` (`Float`): Image collection latency.
    *   `data_source` (`String(512)`): Satellite product details.
    *   `completed_at` (`DateTime(timezone=True)`): End timestamp.
    *   `error_message` (`Text`): Run trace details on failure.
    *   `error_class` (`String(64)`): Error categorization code.
*   **Constraints**: `uq_run_theme` ensures unique `(run_id, theme)`.

### `models/risk_score.py`
*   **One-line purpose**: Compound vulnerability risk summary across active theme parameters.
*   **Type**: ORM model.
*   **Schema**:
    *   `id` (`UUID`): Primary key.
    *   `run_id` (`UUID`): Foreign key to `analysis_runs.id` (Unique).
    *   `aoi_id` (`UUID`): Foreign key to `aois.id`. Compound Index `idx_risk_aoi_time` with `scored_at`.
    *   `overall_score` (`Float`): Weighted composite risk (0-100).
    *   `overall_label` (`String(16)`): LOW\|MODERATE\|HIGH\|CRITICAL.
    *   `flood_risk` (`Float`): Component risk score.
    *   `erosion_risk` (`Float`): Component risk score.
    *   `water_stress` (`Float`): Component risk score.
    *   `vegetation_health` (`Float`): Component risk score.
    *   `landuse_pressure` (`Float`): Component risk score.
    *   `water_sanitation_pressure` (`Float`): Component risk score.
    *   `infrastructure_integrity` (`Float`): Component risk score.
    *   `cross_insights` (`JSONB`): Triggered compound insights list.
    *   `population_in_aoi` (`BigInteger`): Total boundary census.
    *   `population_at_risk` (`BigInteger`): Exposed census.
    *   `scored_at` (`DateTime(timezone=True)`): Default server timestamp.

### `models/alert.py`
*   **One-line purpose**: Alert record created when calculated metrics breach threshold rules.
*   **Type**: ORM model.
*   **Schema**:
    *   `id` (`UUID`): Primary key.
    *   `aoi_id` (`UUID`): Foreign key to `aois.id`. Compound Index `idx_alerts_aoi_time` with `triggered_at`.
    *   `severity` (`String(16)`): INFO\|WATCH\|WARNING\|EMERGENCY. Index `idx_alerts_active` with status, filtered to `status = 'active'`.
    *   `theme` (`String(64)`): Origin theme code.
    *   `alert_type` (`String(64)`): Trigger type classification.
    *   `title` (`String(512)`): Descriptive alert title.
    *   `message` (`Text`): Alert details text.
    *   `metric_value` (`Float`): Breached value.
    *   `metric_unit` (`String(32)`): Units.
    *   `cross_insights` (`JSONB`): Compound insight list, default `list`.
    *   `tile_url` (`Text`): XYZ map url path.
    *   `triggered_at` (`DateTime(timezone=True)`): Default server timestamp.
    *   `expires_at` (`DateTime(timezone=True)`): Alert validity limit.
    *   `resolved_at` (`DateTime(timezone=True)`): Resolution timestamp.
    *   `status` (`String(32)`): active\|resolved\|false_positive.
    *   `dedup_key` (`String(512)`): Unique daily deduplication key.
    *   `email_sent` (`Boolean`): Dispatch tracker.
    *   `push_sent` (`Boolean`): Dispatch tracker.
    *   `dispatched_at` (`DateTime(timezone=True)`): Dispatch timestamp.
