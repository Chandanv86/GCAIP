# GCAIP — Technical Report & Codebase Breakdown

Welcome to the comprehensive, low-level technical report for the Geospatial Climate Adaptation Intelligence Platform (GCAIP). This report breaks down the entire codebase, file-by-file, as it exists. It details imports, function signatures, logic flows, magic numbers, error handling, database schemas, API routes, workers, and frontend structure.

## Document Index (Table of Contents)

1. **[Backend Config & Core](file:///d:/Projects/GCAIP_Project_v2/gcaip/codebase_report/backend_config.md)**
   - `config.py` — Application configuration & environment defaults.
   - `main.py` — FastAPI application entry point, middleware, & exception handling.
   - `db/session.py` — Async/sync database sessions, pooling, & serialization.
   - `db/base.py` — SQLAlchemy declarative base & model auto-registration helper.
   - Database Models (`models/user.py`, `models/aoi.py`, `models/analysis_run.py`, `models/theme_result.py`, `models/risk_score.py`, `models/alert.py`).
   - Database Migrations (`alembic/env.py`, `alembic/versions/001_initial.py`).

2. **[Google Earth Engine (GEE) Layer](file:///d:/Projects/GCAIP_Project_v2/gcaip/codebase_report/gee_layer.md)**
   - `gee/client.py` — Authentication, safe execution, tile fetching, & connectivity test.
   - `gee/processors/base.py` — Abstract base theme processor & ThemeResult serialization.
   - The 10 Theme Processors:
     1. `flood.py` — Sentinel-1 SAR change detection.
     2. `rainfall.py` — GPM IMERG vs. CHIRPS 30-year climatology.
     3. `reservoir.py` — Sentinel-1 + JRC surface water fill fraction.
     4. `mangrove.py` — Sentinel-2 MVI canopy vs. GMW baseline.
     5. `erosion.py` — Shoreline End Point Rate (EPR) tracker.
     6. `vegetation.py` — Sentinel-2 NDVI buffer vs. 5-year climatology.
     7. `landuse.py` — Dynamic World vs. ESA WorldCover change matrix.
     8. `effluent_plume.py` — Water quality/eutrophication indicator.
     9. `coastal_outfall.py` — Marine outfall SPM & Landsat thermal anomaly tracking.
     10. `pipeline_corridor.py` — Pipeline encroachment & NDVI/SAR disturbance buffer monitor.

3. **[Analytical Backend Services](file:///d:/Projects/GCAIP_Project_v2/gcaip/codebase_report/backend_services.md)**
   - `services/orchestrator.py` — Run state creation, task dispatching, & GEE caching.
   - `services/risk_engine.py` — Zonal stats weighting & Composite Risk Score computation.
   - `services/alert_engine.py` — Custom threshold evaluation & Alert model creation.
   - `services/cross_theme.py` — Compound multi-hazard logic & recommended actions.
   - `services/enrichment.py` — WorldPop REST/GEE population & OSM infrastructure overlays.
   - `services/trajectory.py` — Coastal asset erosion EPR impact timeline calculator.
   - Integrations:
     - `integrations/nominatim.py` — OSM Nominatim reverse geocoder.
     - `integrations/overpass.py` — OSM Overpass infrastructure & centerline query client.
     - `integrations/worldpop.py` — Population density lookup with caching.
     - `integrations/sendgrid_client.py` — SendGrid alert email dispatcher.

4. **[Celery Workers & Tasks](file:///d:/Projects/GCAIP_Project_v2/gcaip/codebase_report/workers_tasks.md)**
   - `workers/celery_app.py` — Queue routing, schedules (Celery Beat), & timeouts.
   - `workers/tasks/theme_tasks.py` — Parallel GEE tasks & Redis SSE publishing.
   - `workers/tasks/enrichment_tasks.py` — Zonal enrichment & composite scoring pipeline.
   - `workers/tasks/alert_tasks.py` — Beat scheduled re-analysis, alert evaluation, & tile cleanups.
   - `workers/tasks/report_tasks.py` — Weasyprint PDF report generator.

5. **[FastAPI Route Layers](file:///d:/Projects/GCAIP_Project_v2/gcaip/codebase_report/api_routes.md)**
   - `api/deps.py` — Async database yielders & Redis resource management.
   - `api/v1/health.py` — Service connectivity monitor.
   - `api/v1/aoi.py` — PostGIS shape creation, area checks, & Nominatim reverse geocode.
   - `api/v1/analyze.py` — Analysis triggering, status checks, & Async Redis SSE stream handler.
   - `api/v1/themes.py` — Historical aggregate queries & GEE map tile refresh.
   - `api/v1/timeseries.py` — Continuous daily aggregate charts endpoints.
   - `api/v1/alerts.py` — Alerts list & resolution handlers.
   - `api/v1/reports.py` — PDF generation tasks dispatching & status checks.

6. **[React Frontend Store & State](file:///d:/Projects/GCAIP_Project_v2/gcaip/codebase_report/frontend.md)**
   - `src/store/analysisStore.ts` — Active selection, run status, and layer visibility state.
   - `src/hooks/useSSEStream.ts` — EventSource consumer & Zustand state mutator.
   - `src/types/theme.ts` — Frontend domain models.
   - Overview of key UI views (GlobeView, DrawControl, ValidationPanel, ThemeCard).

---

## Cross-Cutting Summaries

### 1. External Data Sources, APIs, and GEE Assets

This section documents every asset path, external API URL, or remote service called by the GCAIP codebase.

| Data Source / API / GEE Asset ID | File Reference(s) | Purpose |
| :--- | :--- | :--- |
| `COPERNICUS/S2_SR_HARMONIZED` | [vegetation.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/vegetation.py), [mangrove.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/mangrove.py), [erosion.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/erosion.py), [effluent_plume.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/effluent_plume.py), [coastal_outfall.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/coastal_outfall.py), [pipeline_corridor.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/pipeline_corridor.py) | Sentinel-2 surface reflectance, used for NDVI, MVI, NDWI, CDOM, and SPM calculations. |
| `COPERNICUS/S1_GRD` | [reservoir.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/reservoir.py), [erosion.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/erosion.py), [flood.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/flood.py), [pipeline_corridor.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/pipeline_corridor.py) | Sentinel-1 Synthetic Aperture Radar (SAR), used for flood delineation, shoreline changes, water level fills, and corridor backscatter changes. |
| `JRC/GSW1_4/MonthlyHistory` | [reservoir.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/reservoir.py) | Joint Research Centre (JRC) Global Surface Water monthly history. |
| `JRC/GSW1_4/GlobalSurfaceWater` | [reservoir.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/reservoir.py), [flood.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/flood.py) | Permanent water occurrence thresholds & maximum historical extent. |
| `projects/mangrovecapital/assets/GMW/v3/GMW_v3_2020_vec` | [mangrove.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/mangrove.py) | Global Mangrove Watch 2020 vector baseline dataset. |
| `ECMWF/ERA5_LAND/HOURLY` | [erosion.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/erosion.py), [rainfall.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/rainfall.py) | ERA5-Land hourly dataset used for wind speed vectors (wave proxies) and total precipitation fallbacks. |
| `ESA/WorldCover/v200` | [flood.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/flood.py), [coastal_outfall.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/coastal_outfall.py), [landuse.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/landuse.py) | Land cover classifier (built-up, permanent water layers) used for masking and transition analysis. |
| `LANDSAT/LC09/C02/T1_L2` & `LANDSAT/LC08/C02/T1_L2` | [coastal_outfall.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/coastal_outfall.py), [effluent_plume.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/effluent_plume.py) | Landsat-8 and Landsat-9 surface temperature bands (`ST_B10`) and optical bands. |
| `COPERNICUS/S3/OLCI` | [effluent_plume.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/effluent_plume.py) | Sentinel-3 Ocean and Land Colour Instrument (coarse resolution fallback). |
| `GOOGLE/DYNAMICWORLD/V1` | [landuse.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/landuse.py), [pipeline_corridor.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/pipeline_corridor.py) | Near real-time 10m land cover majority classifications. |
| `UMD/hansen/global_forest_change_2023_v1_11` | [landuse.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/landuse.py) | Global Forest Change dataset used to track annual forest loss. |
| `NASA/GPM_L3/IMERG_V07` & `IMERG_V06` | [rainfall.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/rainfall.py) | High-resolution satellite precipitation grids. |
| `JAXA/GPM_L3/GSMaP/v8/operational` | [rainfall.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/rainfall.py) | Global Satellite Mapping of Precipitation (backup). |
| `UCSB-CHG/CHIRPS/DAILY` | [rainfall.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/rainfall.py) | Long-term daily rainfall records used for climatology baselines. |
| `EDF/OGIM/current` | [pipeline_corridor.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/gee/processors/pipeline_corridor.py) | Environmental Defense Fund Oil & Gas Infrastructure Mapping database. |
| OpenStreetMap Nominatim API | [nominatim.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/integrations/nominatim.py) | Reverse geocoding endpoint: `https://nominatim.openstreetmap.org/reverse` |
| OSM Overpass API | [overpass.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/integrations/overpass.py) | Queries infrastructure counts and coordinates: `https://overpass-api.de/api/interpreter` |
| WorldPop API | [worldpop.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/integrations/worldpop.py) | Population counts within bbox: `https://www.worldpop.org/rest/data/pop/wpgpas` |
| SendGrid Mail API | [sendgrid_client.py](file:///d:/Projects/GCAIP_Project_v2/gcaip/gcaip-backend/integrations/sendgrid_client.py) | Outbound email dispatcher. |

---

### 2. Full DB Schema Summary (PostgreSQL + PostGIS + TimescaleDB)

Below is the database structure, combining information from models and migrations.

#### Table: `users`
*   `id` (`UUID`): Primary key. Default: `gen_random_uuid()`.
*   `email` (`VARCHAR(255)`): Unique, index `idx_users_email`.
*   `display_name` (`VARCHAR(255)`): Optional.
*   `hashed_password` (`VARCHAR(255)`): Optional.
*   `is_verified` (`BOOLEAN`): Default `False`.
*   `is_active` (`BOOLEAN`): Default `True`.
*   `tier` (`VARCHAR(32)`): Default `"free"`.
*   `max_aoi_km2` (`DOUBLE PRECISION`): Default `500.0`.
*   `monthly_analysis_count` (`INTEGER`): Default `0`.
*   `preferred_notification_email` (`VARCHAR(255)`): Optional.
*   `timezone` (`VARCHAR(64)`): Default `"UTC"`.
*   `created_at` (`TIMESTAMPTZ`): Default `now()`.
*   `last_login_at` (`TIMESTAMPTZ`): Optional.

#### Table: `aois`
*   `id` (`UUID`): Primary key. Default: `gen_random_uuid()`.
*   `name` (`VARCHAR(512)`): Optional name.
*   `geom` (`GEOMETRY(POLYGON, 4326)`): Mandatory geometry field. GIST index `idx_aois_geom`.
*   `bbox` (`GEOMETRY(POLYGON, 4326)`): Optional boundary envelope.
*   `area_km2` (`DOUBLE PRECISION`): Area check constraint `max_area` (`area_km2 <= 50000`).
*   `country_code` (`VARCHAR(2)`): Optional.
*   `admin_level1` (`VARCHAR(256)`): Province/State.
*   `admin_level2` (`VARCHAR(256)`): District/County.
*   `created_by` (`UUID`): Foreign key to `users.id`, index `idx_aois_user`.
*   `is_public` (`BOOLEAN`): Default `False`.
*   `tags` (`JSONB`): Default `{}`.
*   `created_at` (`TIMESTAMPTZ`): Default `now()`.

#### Table: `analysis_runs`
*   `id` (`UUID`): Primary key. Default: `gen_random_uuid()`.
*   `aoi_id` (`UUID`): Foreign key to `aois.id`. Index `idx_runs_aoi_time` (`aoi_id`, `created_at`).
*   `status` (`VARCHAR(32)`): pending\|running\|complete\|failed. Index `idx_runs_status`.
*   `triggered_by` (`VARCHAR(32)`): user\|schedule\|alert.
*   `date_range_start` (`DATE`): Mandatory start window.
*   `date_range_end` (`DATE`): Mandatory end window.
*   `celery_task_id` (`VARCHAR(255)`): Optional.
*   `started_at` (`TIMESTAMPTZ`): Optional.
*   `completed_at` (`TIMESTAMPTZ`): Optional.
*   `duration_sec` (`DOUBLE PRECISION`): Analysis duration in seconds.
*   `error_message` (`TEXT`): Optional.
*   `gee_quota_used` (`DOUBLE PRECISION`): Optional.
*   `created_at` (`TIMESTAMPTZ`): Default `now()`.

#### Table: `theme_results`
#### Table: `theme_results`
*   `id` (`UUID`): Primary key. Default: `gen_random_uuid()`.
*   `run_id` (`UUID`): Foreign key to `analysis_runs.id`. Index `idx_results_run`.
*   `theme` (`VARCHAR(64)`): Theme name. Index `idx_results_theme_time` (`theme`, `completed_at`).
*   `status` (`VARCHAR(32)`): pending|running|complete|failed|skipped.
*   `tile_url` (`TEXT`): Map server link.
*   `tile_url_expires_at` (`TIMESTAMPTZ`): Expiry time (approx 6h from generation).
*   `vis_params` (`JSONB`): Palette boundaries.
*   `metric_value` (`DOUBLE PRECISION`): Principal numeric metric.
*   `metric_unit` (`VARCHAR(32)`): Units.
*   `metric_label` (`VARCHAR(512)`): Descriptive status label.
*   `stats` (`JSONB`): Zonal summary variables.
*   `enrichment` (`JSONB`): Population, roads, and building overlays.
*   `anomaly_score` (`DOUBLE PRECISION`): Relative z-score distance (0-100).
*   `confidence` (`DOUBLE PRECISION`): Accuracy proxy (0-1).
*   `data_age_hours` (`DOUBLE PRECISION`): Stale time indicator.
*   `data_source` (`VARCHAR(512)`): Satellite/sensor description.
*   `completed_at` (`TIMESTAMPTZ`): Completed time.
*   `error_message` (`TEXT`): Optional stack trace text.
*   `error_class` (`VARCHAR(64)`): Error categorization code (nullable).
*   *Constraint*: `UniqueConstraint("run_id", "theme", name="uq_run_theme")`.

#### Table: `risk_scores`
#### Table: `risk_scores`
*   `id` (`UUID`): Primary key.
*   `run_id` (`UUID`): Foreign key to `analysis_runs.id` (Unique).
*   `aoi_id` (`UUID`): Foreign key to `aois.id`. Index `idx_risk_aoi_time` (`aoi_id`, `scored_at`).
*   `overall_score` (`DOUBLE PRECISION`): Weighted composite (0-100).
*   `overall_label` (`VARCHAR(16)`): LOW|MODERATE|HIGH|CRITICAL.
*   `flood_risk` (`DOUBLE PRECISION`): Optional.
*   `erosion_risk` (`DOUBLE PRECISION`): Optional.
*   `water_stress` (`DOUBLE PRECISION`): Optional.
*   `vegetation_health` (`DOUBLE PRECISION`): Optional.
*   `landuse_pressure` (`DOUBLE PRECISION`): Optional.
*   `water_sanitation_pressure` (`DOUBLE PRECISION`): Optional.
*   `infrastructure_integrity` (`DOUBLE PRECISION`): Optional.
*   `cross_insights` (`JSONB`): Triggered compound insights list.
*   `population_in_aoi` (`BIGINT`): Optional.
*   `population_at_risk` (`BIGINT`): Optional.
*   `scored_at` (`TIMESTAMPTZ`): Default `now()`.

#### Table: `alerts`
*   `id` (`UUID`): Primary key.
*   `aoi_id` (`UUID`): Foreign key to `aois.id`. Index `idx_alerts_aoi_time` (`aoi_id`, `triggered_at`).
*   `severity` (`VARCHAR(16)`): INFO\|WATCH\|WARNING\|EMERGENCY. Index `idx_alerts_active` (`status`, `severity`) filtered to `status = 'active'`.
*   `theme` (`VARCHAR(64)`): Source theme name.
*   `alert_type` (`VARCHAR(64)`): Trigger category code.
*   `title` (`VARCHAR(512)`): Descriptive alert title.
*   `message` (`TEXT`): Trigger description.
*   `metric_value` (`DOUBLE PRECISION`): Trigger value.
*   `metric_unit` (`VARCHAR(32)`): Units.
*   `cross_insights` (`JSONB`): Compound insights.
*   `tile_url` (`TEXT`): Optional alert context map tiles.
*   `triggered_at` (`TIMESTAMPTZ`): Default `now()`.
*   `expires_at` (`TIMESTAMPTZ`): TTL boundary.
*   `resolved_at` (`TIMESTAMPTZ`): Resolution timestamp.
*   `status` (`VARCHAR(32)`): active\|resolved\|false_positive.
*   `dedup_key` (`VARCHAR(512)`): Unique constraint to prevent multiple alerts on same day (`aoi_id:alert_type:date`).
*   `email_sent` (`BOOLEAN`): Default `False`.
*   `push_sent` (`BOOLEAN`): Default `False`.
*   `dispatched_at` (`TIMESTAMPTZ`): Dispatch timestamp.

#### Table: `metric_timeseries` (TimescaleDB Hypertable)
*   `time` (`TIMESTAMPTZ`): Time bucket dimension key.
*   `aoi_id` (`UUID`): Target boundary. Index `idx_ts_aoi_theme` (`aoi_id`, `theme`, `time DESC`).
*   `theme` (`TEXT`): Theme code.
*   `metric_name` (`TEXT`): Metric name.
*   `value` (`DOUBLE PRECISION`): Recorded point.
*   `confidence` (`DOUBLE PRECISION`): Confidence score.
*   `source` (`TEXT`): Data source.
*   `flags` (`JSONB`): Custom markers.

#### Materialized View: `metric_daily` (TimescaleDB Continuous Aggregate)
Calculates daily stats from `metric_timeseries`:
*   `day`: `time_bucket('1 day', time)`.
*   `aoi_id`, `theme`, `metric_name`, `avg_value`, `min_value`, `max_value`, `avg_confidence`.

---

### 3. Celery Task Inventory

### 3. Celery Task Inventory
| Queue | Task Name | Trigger | Purpose |
| :--- | :--- | :--- | :--- |
| `gee_tasks` | `flood_task` | Orchestrator (`/analyze`) | Runs SAR flood pipeline. |
| `gee_tasks` | `rainfall_task` | Orchestrator (`/analyze`) | Runs CHIRPS/GPM rainfall pipeline. |
| `gee_tasks` | `reservoir_task` | Orchestrator (`/analyze`) | Runs JRC reservoir volume pipeline. |
| `gee_tasks` | `mangrove_task` | Orchestrator (`/analyze`) | Runs Sentinel-2 mangrove loss pipeline. |
| `gee_tasks` | `erosion_task` | Orchestrator (`/analyze`) | Runs SAR coastal erosion pipeline. |
| `gee_tasks` | `vegetation_task` | Orchestrator (`/analyze`) | Runs Sentinel-2 NDVI buffer pipeline. |
| `gee_tasks` | `landuse_task` | Orchestrator (`/analyze`) | Runs Dynamic World land use pipeline. |
| `gee_tasks` | `effluent_plume_task` | Orchestrator (`/analyze`) | Runs optical effluent plume pipeline. |
| `gee_tasks` | `coastal_outfall_task` | Orchestrator (`/analyze`) | Runs marine outfall plume pipeline. |
| `gee_tasks` | `pipeline_corridor_task`| Orchestrator (`/analyze`) | Runs pipeline corridor disturbance pipeline. |
| `enrichment_tasks` | `compute_risk_score_task` | `_check_run_complete` | Waits for all GEE tasks, calculates composite risk. |
| `alert_tasks` | `evaluate_alerts_task` | `compute_risk_score_task` | Checks thresholds post-analysis, writes Alerts. |
| `alert_tasks` | `dispatch_email_alert_task` | `evaluate_alerts_task` | Dispatches SendGrid emails for new Alerts. |
| `alert_tasks` | `scheduled_reanalysis` | Celery Beat (Cron) | Bulk-triggers `/analyze` on public AOIs. |
| `alert_tasks` | `cleanup_expired_tiles` | Celery Beat (Cron) | Clears stale XYZ tile URLs from DB. |
| `report_tasks` | `generate_pdf_report_task` | `/api/v1/reports` | Asynchronously builds a PDF using reportlab. |

### 4. Codebase Inconsistencies & Logical Gaps

Below are findings from reading the codebase that could cause bugs, database discrepancies, or configuration drift.

1. **Active Themes Mismatch (Celery vs. FastAPI)**:
   * **Issue**: The active GEE processors are defined as a subset in `workers/tasks/theme_tasks.py` (`ACTIVE_THEMES = {"rainfall", "landuse", "effluent_plume", "coastal_outfall", "pipeline_corridor"}`). However, `services/orchestrator.py` lists the default dispatch themes as `["rainfall", "landuse", "effluent_plume", "coastal_outfall", "pipeline_corridor"]` but leaves `flood`, `reservoir`, `erosion`, `mangrove`, and `vegetation` out.
   * **Risk**: If the frontend requests an inactive theme (e.g. `flood` or `erosion`), the orchestrator will still dispatch it because `theme_tasks.py` registers all 10 tasks, but the `AlertEngine` disabled themes block prevents alert generation for them, and `RiskEngine` omits them from the weighted score. This leads to configuration discrepancies.
2. **Missing PostGIS Schema Mapping in SQLAlchemy**:
   * **Issue**: In `models/aoi.py`, `geom` and `bbox` are defined using GeoAlchemy2 `Geometry` fields. However, in `alembic/versions/001_initial.py`, they are created as simple `sa.Column("geom", sa.Text(), nullable=False)` and later updated to PostGIS geometries via raw SQL execution.
   * **Risk**: Migrations executed on fresh DB configurations must ensure that the PostGIS extension is loaded first, and the raw SQL conversion will fail if the spatial database is not properly initialized.
3. **Database URL Sync/Async String Replacements**:
   * **Issue**: Celery workers run synchronously and cannot use the async `asyncpg` dialect. The backend handles this by dynamically replacing the driver in the database string: `.replace("postgresql+asyncpg://", "postgresql+psycopg2://")` in `theme_tasks.py`, `enrichment_tasks.py`, `alert_tasks.py`, and `report_tasks.py`.
   * **Risk**: If a developer changes the base `.env` connection string to use another format (such as another host or a different scheme), the driver-replacement logic will silently fail to match, crashing Celery tasks at runtime with dialect errors.
4. **Temporary Directory for Reports**:
   * **Issue**: `report_tasks.py` sets `REPORT_OUTPUT_DIR = "/tmp/gcaip_reports"`.
   * **Risk**: This works on Unix-like filesystems but causes issues on Windows (which uses `C:\tmp` or fails unless user has matching privileges) or in stateless container runtimes (where local file storage is lost). The PDF reports should be written to the system's temp path using the python `tempfile` module or uploaded immediately to S3/GCS.
5. **Deduplication Key Clock Slip**:
   * **Issue**: In `alert_engine.py`, the `dedup_key` uses `date.today().isoformat()` which relies on the local server time. The alerts themselves are stamped with UTC timestamps.
   * **Risk**: If the server timezone drifts or is different from UTC, duplicate alerts could be triggered for boundaries close to midnight.
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
### `models/theme_result.py`
*   **One-line purpose**: Individual Google Earth Engine theme execution result data.
*   **Type**: ORM model.
*   **Schema**:
    *   `id` (`UUID`): Primary key.
    *   `run_id` (`UUID`): Foreign key to `analysis_runs.id`. Index `idx_results_run`.
    *   `theme` (`String(64)`): Theme code (e.g. flood|landuse|effluent_plume|coastal_outfall|pipeline_corridor). Compound Index `idx_results_theme_time` with `completed_at`.
    *   `status` (`String(32)`): pending|running|complete|failed|skipped.
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
    *   `error_class` (`String(64)`): Error categorization code (e.g., GEEQuotaError, timeout), nullable. Added in migration `002_schema_drift_fixes`.
*   **Constraints**: `uq_run_theme` ensures unique `(run_id, theme)`.

### `models/risk_score.py`
### `models/risk_score.py`
*   **One-line purpose**: Compound vulnerability risk summary across active theme parameters.
*   **Type**: ORM model.
*   **Schema**:
    *   `id` (`UUID`): Primary key.
    *   `run_id` (`UUID`): Foreign key to `analysis_runs.id` (Unique).
    *   `aoi_id` (`UUID`): Foreign key to `aois.id`. Compound Index `idx_risk_aoi_time` with `scored_at`.
    *   `overall_score` (`Float`): Weighted composite risk (0-100).
    *   `overall_label` (`String(16)`): LOW|MODERATE|HIGH|CRITICAL.
    *   `flood_risk` (`Float`): Component risk score.
    *   `erosion_risk` (`Float`): Component risk score.
    *   `water_stress` (`Float`): Component risk score.
    *   `vegetation_health` (`Float`): Component risk score.
    *   `landuse_pressure` (`Float`): Component risk score.
    *   `water_sanitation_pressure` (`Float`): Component risk score. Added in migration `002_schema_drift_fixes`.
    *   `infrastructure_integrity` (`Float`): Component risk score. Added in migration `002_schema_drift_fixes`.
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
# Google Earth Engine (GEE) Integration Layer

All geospatial analysis in GCAIP is executed on Google Earth Engine. This section breaks down the client connection, base processor, and the 10 thematic analytical modules.

---

## 1. Connection & Base Processor

### `gee/client.py`
*   **One-line purpose**: GEE connection, credentials handling, retry logic wrapper, and coordinate utilities.
*   **Functions & Signatures**:
    *   `initialize() -> None`: Thread-safe connection using Service Account credentials. Resolves path using `settings.GEE_CREDENTIALS_PATH`. Uses `settings.GEE_PROJECT` and `opt_url="https://earthengine.googleapis.com"`.
    *   `_classify_error(exc: Exception) -> GEEError`: Translates raw GEE exceptions into typed subclasses (`GEEQuotaError` if matches rate/memory limits, `GEEAssetNotFoundError` if matches missing assets/dates, or `GEETransientError` for other failures).
    *   `safe_call(fn: Callable, *args: Any, retries: int = settings.GEE_MAX_RETRIES, timeout: int = settings.GEE_TIMEOUT_SECONDS, **kwargs: Any) -> Any`: Executes a GEE call wrapped in a retry loop. Retries with exponential backoff (`2 ** attempt` seconds) only for `GEETransientError`. Instantly raises `GEEQuotaError` and `GEEAssetNotFoundError` to avoid wasting compute credits.
    *   `get_tile_url(image: ee.Image, vis_params: dict) -> tuple[str, datetime]`: Renders a GEE image to an XYZ URL template. Computes expiry time as current UTC time plus 6 hours.
    *   `get_stats(image: ee.Image, aoi: ee.Geometry, scale: int = settings.GEE_SCALE_DEFAULT, reducer: ee.Reducer | None = None, max_pixels: int = 1e10) -> dict[str, Any]`: Zonal statistics calculator. Defaults to `ee.Reducer.mean()`. Sets `bestEffort=True` to scale down resolution if the pixel count limit is exceeded.
    *   `geojson_to_ee_geometry(geojson: dict) -> ee.Geometry`: Standardizes coordinates from GeoJSON polygons or features to GEE-compatible geometries.
    *   `test_connection() -> dict[str, Any]`: Checks GEE connectivity by reading from the JRC occurrence layer at point `[8.75, 3.75]`. Returns connection latency.
*   **Thresholds & Constants**:
    *   `settings.GEE_MAX_RETRIES` = `3`
    *   `settings.GEE_TIMEOUT_SECONDS` = `120`
    *   Backoff wait: `1s`, `2s`, `4s`

### `gee/processors/base.py`
*   **One-line purpose**: Declarative base definition class for GEE theme processors and result serialization.
*   **Definitions**:
    *   `class ThemeResult`: Dataclass containing the analysis outputs. Includes `to_dict()`, `error_result()`, and `not_applicable_result()` helper methods.
    *   `class BaseThemeProcessor(ABC)`: Abstract base class requiring subclasses to implement `compute()`.
*   **Key Helper Methods**:
    *   `get_reference_period(end_date: str, years_back: int = 3) -> tuple[str, str]`: Computes a same-season 30-day window N years back.
    *   `apply_s2_cloud_mask(image: ee.Image) -> ee.Image`: Sentinel-2 cloud masking. Reads the Scene Classification Layer (`SCL`) and keeps only values `4` (vegetation), `5` (bare soil), and `6` (built-up).
    *   `compute_anomaly_score(current_value: float, historical_mean: float, historical_std: float) -> float`: Computes z-score: `z = abs(current - mean) / std`. Normalizes this to a `0-100` scale: `score = min(100.0, (z / 3.0) * 100.0)`.
    *   `data_age_from_millis(millis: float | None) -> float`: Converts GEE image timestamp to age in hours.

---

## 2. Active Theme Processors

### `rainfall.py` (Theme 2)
*   **One-line purpose**: Precipitation accumulation tracking and Standardized Precipitation Index (SPI) z-score calculation.
*   **Type**: Active Theme Processor.
*   **Algorithms & Logic Flow**:
    1.  Tries to load GPM IMERG V07. Falls back to IMERG V06, then hourly ERA5-Land (converting m to mm), and finally GSMaP v8.
    2.  Extracts the latest scene timestamp. If data is stale (> 3 days), it shifts the end date to match availability.
    3.  Calculates 24-hour, 7-day, and 30-day accumulated rainfall.
    4.  Extracts max 30-minute rate. Flags flash-flood risk if rate exceeds `50 mm/hr`.
    5.  Calculates 7-day and 30-day baseline means and standard deviations from CHIRPS daily data (1991-2020 baseline WMO period).
    6.  Computes 7-day and 30-day SPI z-scores and maps them to descriptive labels (e.g., Extremely Wet, Moderately Dry).
*   **Constants & Thresholds**:
    *   `VIS_RAINFALL` palette boundaries: `[0, 500]` mm.
    *   Flash flood limit = `50.0 mm/hr`.
    *   SPI bins: `2.0` (Extremely Wet), `1.5` (Very Wet), `1.0` (Moderately Wet), `-1.0` (Near Normal), `-1.5` (Moderately Dry), `-2.0` (Very Dry).
    *   CHIRPS baseline scale = `5500` (5.5 km).

### `landuse.py` (Theme 7)
*   **One-line purpose**: Tracks vegetation clearance and urban expansion.
*   **Type**: Active Theme Processor.
*   **Algorithms & Logic Flow**:
    1.  Loads Dynamic World majority classification. Progressively widens search window (default → 15d → 30d → 90d) if no cloud-free images are found.
    2.  If Dynamic World is completely unavailable, it falls back to a static 2021 ESA WorldCover map re-mapped to DW-compatible classes.
    3.  Compares the current classification with the 2021 ESA WorldCover baseline to detect land cover transitions.
    4.  Calculates transition areas in hectares (e.g. tree-to-built, tree-to-crops).
    5.  Loads UMD Hansen GFW forest loss layers to measure deforestation.
    6.  Estimates watershed runoff increase using USDA Curve Number rules (CN increases by `~40` for tree-to-built, `~15` for tree-to-crops).
*   **Constants & Thresholds**:
    *   Hansen GFW recent years window = last `3` years (typically 2021-2023).
    *   `VIS_LANDUSE` maps classes `0` (water) through `8` (snow).

### `effluent_plume.py` (Theme 8)
### `effluent_plume.py` (Theme 8)
*   **One-line purpose**: Detects water-quality anomaly plumes (elevated chlorophyll-a / turbidity) into inland water bodies.
*   **Type**: GEE Processor.
*   **Logic**:
    1. Validates optical imagery (S2 Harmonized) using a progressive fallback cascade: S2 default -> S2 +15d -> S2 +30d -> S2 relaxed (60% cloud) -> Landsat 8/9 default -> Landsat 8/9 +30d -> Sentinel-3 OLCI.
    2. Builds composite and computes MNDWI (`> 0.1` threshold) to isolate water.
    3. Computes NDCI (chlorophyll proxy, `> 0.05` threshold) and NDTI (turbidity proxy, `> 0.10` threshold).
    4. Computes baseline over 1-year prior for relative comparison.
    5. Retrieves zonal statistics explicitly for `plume_area_km2`, `water_area_km2`, `ndci_mean`, `ndti_mean`.
    6. Ensures raster bounding via `.clip(aoi)` in visualization tile generation.
    7. Computes `anomaly_score` based on plume-to-water area ratio (capped at 100).
*   **Constants**: `NDCI_THRESHOLD = 0.05`, `NDTI_THRESHOLD = 0.10`, `MNDWI_THRESHOLD = 0.1`, `CLOUD_COVER_MAX = 35`, `WINDOW_DAYS_FALLBACK_LANDSAT = 30`.
*   **Error Handling**: Raises `GEEAssetNotFoundError` if no optical scenes across all 7 fallback tiers. Evaluates lazy objects (`aggregate_max`) dynamically to prevent `.getInfo()` type errors in unit tests.

### `coastal_outfall.py` (Theme 9)
### `coastal_outfall.py` (Theme 9)
*   **One-line purpose**: Detects marine discharge plumes at coastal outfalls and calculates extent, dispersion bearing, and thermal anomaly.
*   **Type**: GEE Processor.
*   **Logic**:
    1. Early applicability check: Verifies AOI contains at least 10 pixels (100m scale) of `ESA/WorldCover/v200` permanent water (class 80). Yields `not_applicable_result` if purely terrestrial.
    2. Loads S2 with a 4-tier fallback cascade (default -> +15d -> +30d -> relaxed 60%).
    3. Excludes glint via SWIR1 threshold (`B11 < 0.02`).
    4. Computes Suspended Particulate Matter (SPM) using `SPM_A_COEFF = 355.85` and `SPM_C_COEFF = 0.1728`.
    5. Computes CDOM index (`B2/B3`).
    6. Applies a Sobel edge detector to the combined SPM/CDOM signal to isolate the plume front using a dynamic 90th percentile threshold.
    7. Calculates dispersion bearing by comparing plume centroid against outfall anchor point (from `aoi_geojson["properties"]["outfall_point"]` or AOI centroid).
    8. Loads Landsat 8/9 thermal (Band 10) to compute delta Sea Surface Temperature (SST) in Celsius (`> 1.5C` flags thermal plume).
    9. Ensures raster bounding via `.clip(aoi)` in visualization tile generation.
*   **Constants**: `GLINT_B11_THRESHOLD = 0.02`, `CLOUD_COVER_MAX = 35`, `THERMAL_PLUME_DELTA_C = 1.5`.
*   **Error Handling**: Emits structured exceptions on data exhaustion or SWIR filter masking out all water pixels. Converts type-error prone None/NaN values from stats payload manually.

### `pipeline_corridor.py` (Theme 10)
### `pipeline_corridor.py` (Theme 10)
*   **One-line purpose**: Monitors a buffered linear corridor along real pipeline routes for vegetation disturbance, soil exposure, and encroachment.
*   **Type**: GEE Processor.
*   **Logic**:
    1. Pipeline geometry resolution (priority order): OSM `pipeline_geometry` injected in AOI properties -> `EDF/OGIM/current` GEE FeatureCollection -> `EDF/OGIM/current` with 2km buffer retry -> Raises Error.
    2. Buffers geometry by `buffer_m` (default 200m).
    3. Sentinel-1 GRD IW/VV: Loads descending -> ascending -> +15d -> +30d window cascade. Computes ratio of current backscatter against 90-120 day baseline. Masks ratio > `RATIO_DISTURBANCE_THRESHOLD` (`1.6`).
    4. Sentinel-2 NDVI: Computes current NDVI against 30-90 day baseline. Masks drop > `NDVI_DROP_THRESHOLD` (`0.15`).
    5. Dynamic World V1: Identifies bare/built (classes 6 and 7) encroachment.
    6. Ensures raster bounding via `.clip(aoi)` in visualization tile generation.
    7. Simplifies vector geometry (maxError=50m) and returns `pipeline_corridor_geojson` to frontend.
*   **Constants**: `DEFAULT_BUFFER_M = 200`, `RATIO_DISTURBANCE_THRESHOLD = 1.6`, `NDVI_DROP_THRESHOLD = 0.15`, `CLOUD_COVER_MAX = 40`, `OGIM_ASSET_ID = "EDF/OGIM/current"`.
*   **Error Handling**: Calculates date string offsets locally via Python `datetime` module to bypass GEE Joda-Time eval mismatch issues.


## 3. Disabled Theme Processors

*These processors are fully coded but are currently disabled in production dispatch loops.*

### `flood.py` (Theme 1)
*   **One-line purpose**: Delineates flood extents using Sentinel-1 SAR change detection.
*   **Type**: Inactive Theme Processor.
*   **Algorithms & Logic Flow**:
    1.  Loads current Sentinel-1 scenes (descending pass first, falling back to ascending).
    2.  Builds a current VV backscatter composite and converts to decibels: `VV_dB = mean(VV).log10() * 10`.
    3.  Builds a reference VV decibel composite for the same calendar month over the prior 2 years.
    4.  Calculates backscatter difference (`diff = current - reference`). Flags flood pixels where difference `< -3.0 dB`.
    5.  Masks permanent water bodies (JRC Global Surface Water occurrence > 80%).
    6.  Identifies urban flood risk zones by overlapping detected flood pixels with ESA WorldCover built-up classes (class 50).
    7.  Computes near-flood risk zones for marginal signals (`diff` between `-1.0` and `-3.0` dB).
*   **Constants & Thresholds**:
    *   `flood_threshold_db` = `-3.0 dB`
    *   Urban class = `50`
    *   Water occurrence mask = `80`
    *   `VIS_FLOOD` classes: `1` (flooded), `2` (near-flood), `3` (urban flood).

### `reservoir.py` (Theme 3)
*   **One-line purpose**: Computes reservoir fill fraction, trends, and spillway risk.
*   **Type**: Inactive Theme Processor.
*   **Algorithms & Logic Flow**:
    1.  Loads Sentinel-1 GRD imagery. If no scenes are found, falls back to the permanent water class in JRC Monthly History.
    2.  Delineates water surface area using a SAR threshold: `VV < -15.0 dB`.
    3.  Calculates the current water area.
    4.  Compares results with the maximum historical extent (JRC Global Surface Water `max_extent`) to determine the fill fraction percentage.
    5.  Compares current area with the prior year to track annual changes.
    6.  Measures the fill rate over the past 30 days to classify the reservoir trend as FILLING, DRAINING, or STABLE.
    7.  Calculates days to full/empty based on the fill rate.
    8.  Categorizes spillway risk based on fill percentage and trend.
*   **Constants & Thresholds**:
    *   SAR water threshold = `-15.0` dB
    *   Spillway Risk categorization:
        *   `CRITICAL` if fill fraction `>= 95%`.
        *   `HIGH` if fill fraction `>= 88%` and fill rate `> 0.2%/day`.
        *   `MEDIUM` if fill fraction `>= 80%`.
        *   `LOW-MEDIUM` if fill fraction `>= 70%`.
        *   `LOW` otherwise.

### `mangrove.py` (Theme 4)
*   **One-line purpose**: Tracks mangrove canopy extent and carbon density changes.
*   **Type**: Inactive Theme Processor.
*   **Algorithms & Logic Flow**:
    1.  Loads Sentinel-2 cloud-free composites.
    2.  Calculates Mangrove Vegetation Index: `MVI = SWIR1 / NIR` (S2 Bands `B11 / B8`). Canopy is flagged where `MVI > 1.0`.
    3.  Measures canopy health using mean NDVI over the detected mangrove pixels.
    4.  Compares results with the 2020 Global Mangrove Watch (GMW v3) vector baseline.
    5.  Calculates net canopy changes (hectares gained and lost).
    6.  Estimates total carbon storage and annual sequestration changes.
*   **Constants & Thresholds**:
    *   `CARBON_DENSITY_TCO2_HA` = `200.0` tCO2e/ha (conservative estimate)
    *   Mangrove canopy MVI threshold = `1.0`.

### `erosion.py` (Theme 5)
*   **One-line purpose**: Measures shoreline erosion rates using multi-temporal Sentinel-1 water masks.
*   **Type**: Inactive Theme Processor.
*   **Algorithms & Logic Flow**:
    1.  Loads current Sentinel-1 scenes and masks water where `VV < -15.0 dB`.
    2.  Loads Sentinel-1 reference imagery from 24 months prior.
    3.  Detects shoreline changes: erosion (was land, now water) and accretion (was water, now land).
    4.  If reference SAR imagery is missing, falls back to Sentinel-2 NDWI (`(Green - NIR) / (Green + NIR) > 0.0`).
    5.  Calculates End Point Rate (EPR) in meters per year: `EPR = (accretion_area - erosion_area) / (estimated_coastline_length * 2.0)`.
    6.  Loads ERA5 wind components (`u` and `v`) to calculate wind speed as a wave proxy.
*   **Constants & Thresholds**:
    *   `VIS_EROSION` ranges from `-5` (retreat) to `+5` (accretion) m/yr.
    *   Erosion time window = `2.0` years.
    *   Storm wave risk classification: `HIGH` if wind speed exceeds `15 m/s`, `MEDIUM` if `> 10 m/s`, otherwise `LOW`.

### `vegetation.py` (Theme 6)
*   **One-line purpose**: Measures vegetation buffer health compared to a 5-year climatological baseline.
*   **Type**: Inactive Theme Processor.
*   **Algorithms & Logic Flow**:
    1.  Loads Sentinel-2 scenes with cloud cover `< 30%`.
    2.  Calculates NDVI: `(NIR - Red) / (NIR + Red)` (S2 Bands `B8 / B4`).
    3.  Computes a same-season 30-day historical mean NDVI over the prior 2 to 5 years.
    4.  Calculates the z-score anomaly relative to this historical baseline.
    5.  Measures the percentage of degraded vegetation (NDVI < 0.3) within the AOI.
    6.  Checks for dieback: flags if current NDVI drops by `> 0.15` compared to the prior 90-day composite.
*   **Constants & Thresholds**:
    *   Cloud filter limit = `30%`.
    *   Vegetation health categories: `GOOD` if NDVI `>= 0.6`, `MODERATE` if `>= 0.4`, `STRESSED` if `>= 0.2`, otherwise `DEGRADED`.
    *   Dieback limit = `-0.15` NDVI change.
    *   Degraded vegetation threshold = `0.3`.
# Analytical Backend Services & Integrations

This section describes the services that coordinate analysis runs, calculate composite risk scores, evaluate alerts, query external database APIs, and project erosion timelines.

---

## 1. Core Services

### `services/orchestrator.py`
### `services/orchestrator.py`
*   **One-line purpose**: Entry point that creates `AnalysisRun`, pre-creates `ThemeResult` stubs, and dispatches Celery tasks.
*   **Type**: Business logic service.
*   **Classes/Functions**:
    *   `ALL_THEMES` (list): Current active themes (`rainfall`, `landuse`, `effluent_plume`, `coastal_outfall`, `pipeline_corridor`).
    *   `AnalysisOrchestrator` (class): The main orchestrator layer.
    *   `dispatch_async(db, aoi_id, aoi_geojson, date_range, themes, triggered_by) -> str`: The FastAPI entry point. Creates the `AnalysisRun` DB record, pre-creates pending `ThemeResult` rows synchronously via flush, generates a cache key, and invokes `workers.tasks.theme_tasks.dispatch_all_themes()`. Handles Celery/Redis connection failures by explicitly failing the run and raising a `503 Service Unavailable` error instead of leaving the run orphaned in `running` state.
    *   `dispatch(...) -> str`: The synchronous version for Celery Beat scheduled tasks, instantiating its own `psycopg2` sync session.
    *   `_default_date_range() -> tuple`: Defaults to `(today - 30 days, today)`.
    *   `_make_cache_key(aoi_geojson, start, end) -> str`: Generates a SHA256 deterministic hash for GEE result caching to avoid quota waste.

### `services/risk_engine.py`
### `services/risk_engine.py`
*   **One-line purpose**: Computes a single weighted composite risk score (0-100) aggregating all active themes.
*   **Type**: Business logic service.
*   **Classes/Functions**:
    *   `WEIGHTS`: `water_stress` (30%), `landuse` (25%), `water_sanitation` (25%), `infrastructure` (20%).
    *   `RiskScore` (dataclass): Container for sub-indices and overall score.
    *   `RiskEngine` (class): The core aggregation calculator.
    *   `compute(results_by_theme) -> RiskScore`: Computes overall composite risk.
    *   `_water_stress_index`: Combines reservoir fill, rainfall SPI, and cross-links pollution anomaly (effluent/coastal outfall weighted 15%).
    *   `_landuse_pressure_index`: Combines runoff increase and changed area. Cross-links pipeline corridor encroachment.
    *   `_pollution_risk_index`: Max anomaly of effluent plume and coastal outfall.
    *   `_infrastructure_integrity_index`: Translates pipeline corridor anomaly.
    *   `_label(score)`: Maps numeric score to LOW/MODERATE/HIGH/CRITICAL label.

### `services/alert_engine.py`
### `services/alert_engine.py`
*   **One-line purpose**: Evaluates analytical thresholds and creates deduplicated `Alert` records.
*   **Type**: Business logic service.
*   **Classes/Functions**:
    *   `THRESHOLDS` (dict): 10 core alerting rules including `flood_active`, `spillway_risk`, `erosion_storm`, `mangrove_loss`, `extreme_rainfall`, `effluent_plume_detected`, `thermal_plume_active`, `spm_spike`, `corridor_encroachment`, `corridor_disturbance`.
    *   `AlertEngine` (class): Evaluates rules against `theme_results`.
    *   `AlertEngine.evaluate(aoi_id, run_id, theme_results, session) -> list`: Iterates active themes, checks thresholds and `confidence_min`. Generates `dedup_key = f"{aoi_id}:{rule['alert_type']}:{today_utc}"` to prevent duplicate alerts on the same day. Uses UTC date for deduplication to prevent timezone drift duplicates near midnight (P7 fix). Upserts alerts to DB.

### `services/cross_theme.py`
### `services/cross_theme.py`
*   **One-line purpose**: Compound correlation engine detecting interconnected risks across multiple themes.
*   **Type**: Business logic service.
*   **Classes/Functions**:
    *   `CrossInsight` (dataclass): Structured payload for compound risk output (id, text, severity, action).
    *   `CrossThemeCorrelator` (class): Executes correlation rules.
    *   `CrossThemeCorrelator.evaluate(stats_by_theme) -> list[CrossInsight]`: Returns sorted list of triggered cross-theme insights. Includes 9 compound rules (e.g. Reservoir + Rainfall → Spillway Risk, Rainfall + Land Use → Runoff Amplification, Rainfall + Effluent Plume → Runoff Driven Plume, Land Use + Pipeline Corridor → Encroachment Confirmed). Several rules are currently preserved but inactive due to globally disabled themes.

### `services/enrichment.py`
*   **One-line purpose**: Converts raw areas and change metrics into human-centric impact metrics.
*   **Type**: Data Enricher.
*   **Functions & Logic Flow**:
    *   `enrich_flood(aoi_geojson, flood_stats) -> dict`: Extracts the bounding box, queries population within the box via WorldPop, and queries schools, hospitals, and road lengths using OSM Overpass.
    *   `enrich_erosion(aoi_geojson, erosion_stats, osm_assets) -> dict`: Queries population, general infrastructure, and coastal assets within 1000m of the shoreline. If the coastline is eroding (EPR < 0), it projects the impact timeline using `TrajectoryCalculator`.
    *   `enrich_mangrove(aoi_geojson, mangrove_stats) -> dict`: Queries settlements within 5km of the coastal boundary to estimate the population protected by the mangrove buffer.
*   **Formatting Rules**:
    *   `_format_population(count: int) -> str`: Formats population counts (e.g. `count >= 10M` formatted as `X.XM`, `count >= 100k` formatted as `X.X lakh`, and `count >= 1000` formatted as `X.Xk`).

### `services/trajectory.py`
*   **One-line purpose**: Calculates the time-to-impact for coastal infrastructure based on current erosion rates.
*   **Type**: Mathematical Projection Tool.
*   **Functions & Logic Flow**:
    *   `compute(coastal_assets: list[dict], erosion_rate_m_yr: float) -> list[dict]`:
        1.  Loops through coastal assets (each containing name, type, and distance from shoreline).
        2.  Calculates years to impact: `years = distance_m / erosion_rate_m_yr`.
        3.  Computes the expected impact year: `current_year + int(years)`.
        4.  Sorts assets by years-to-impact (nearest first).

---

## 2. External Integration Clients

### `integrations/nominatim.py`
*   **One-line purpose**: Geocodes centroids to populate country and administrative attributes.
*   **Type**: API Client (HTTPX).
*   **API Calls**: Sends an async GET request to `settings.NOMINATIM_BASE_URL/reverse` with lat/lon parameters, JSONv2 format, and a 2.0s timeout.

### `integrations/overpass.py`
*   **One-line purpose**: Queries OpenStreetMap Overpass APIs for road networks, utility lines, and infrastructure counts.
*   **Type**: API Client (HTTPX).
*   **Features**:
    *   Uses a 24-hour cache key (`gcaip:osm:`) stored in Redis.
    *   Implements a 10s backoff retry loop if the Overpass API returns a 429 Rate Limit response.
    *   Calculates road segment lengths using Haversine approximations.
*   **API Queries**:
    *   *Infrastructure*: Queries nodes matching school, hospital, or clinic, and ways matching motorways, trunk, primary, secondary, or tertiary highways.
    *   *Coastal Assets*: Queries roads, places (village/town/hamlet), and amenities within the bounding box.
    *   *Pipelines*: Queries ways matching `man_made=pipeline` and returns them as a GeoJSON FeatureCollection.

### `integrations/worldpop.py`
*   **One-line purpose**: Fetches spatial population counts from WorldPop or GEE fallbacks.
*   **Type**: API Client (HTTPX/GEE).
*   **Logic Flow**:
    1.  Calculates a bounding box hash.
    2.  Checks for cached values in Redis.
    3.  Sends a GET request to the WorldPop API: `/pop/wpgpas` with year 2020 and boundary parameters.
    4.  If the API call fails or times out, it falls back to a GEE zonal sum query using the `WorldPop/GP/100m/pop` dataset.

### `integrations/sendgrid_client.py`
*   **One-line purpose**: Dispatches alert notifications to users via email.
*   **Type**: SMTP API Client.
*   **API Calls**: Sends alert emails via SendGrid's API. Uses the sender address configured in `settings.SENDGRID_FROM_EMAIL` and defaults to sending to the same address.
# Celery Workers & Task Pipelines

GCAIP relies on Celery for asynchronous task execution, dividing workloads among specialized queues. This section details the Celery application setup and task handlers.

---

## 1. Celery Application Setup

### `workers/celery_app.py`
*   **One-line purpose**: Configures the Celery application, task routes, and scheduled maintenance jobs.
*   **Type**: Worker Configuration.
*   **Key Configurations**:
    *   Imports all models to resolve database relations during background tasks.
    *   Includes task modules: `theme_tasks`, `enrichment_tasks`, `alert_tasks`, and `report_tasks`.
    *   Enables eager execution mode (`task_always_eager = True`) in development environments.
*   **Timeout & Queue Settings**:
    *   `task_soft_time_limit` = `180` seconds (3 minutes)
    *   `task_time_limit` = `240` seconds (4 minutes)
    *   `result_expires` = `86400` seconds (24 hours)
    *   `worker_prefetch_multiplier` = `1` (prefetch disabled to process tasks one at a time)
*   **Task Queues & Routing**:
    *   `workers.tasks.theme_tasks.*` → `gee_tasks`
    *   `workers.tasks.enrichment_tasks.*` → `enrichment_tasks`
    *   `workers.tasks.alert_tasks.*` → `alert_tasks`
    *   `workers.tasks.report_tasks.*` → `default`
*   **Celery Beat Schedules**:
    *   `scheduled-reanalysis`: Calls `alert_tasks.scheduled_reanalysis` every 6 hours (`crontab(minute=0, hour="*/6")`).
    *   `cleanup-expired-tiles`: Calls `alert_tasks.cleanup_expired_tiles` every 6 hours (`crontab(minute=30, hour="*/6")`).

---

## 2. Task Handlers

### `workers/tasks/theme_tasks.py`
### `workers/tasks/theme_tasks.py`
*   **One-line purpose**: Individual Celery tasks for all 10 GEE theme processors.
*   **Type**: Celery Task Module.
*   **Classes/Functions**:
    *   `GEETask` (class): Base Celery task. Handles `SoftTimeLimitExceeded` to gracefully write timeouts to the DB as `failed` (preventing runs from getting stuck in `running` state indefinitely).
    *   `_run_theme(...) -> dict`: Shared execution wrapper that handles Redis caching, DB persistence (`_store_theme_result`), SSE publishing (`_publish_theme_event`), and checking for run completion (`_check_run_complete`). Stores structured `error_class` if present.
    *   Tasks: `flood_task`, `rainfall_task`, `reservoir_task`, `mangrove_task`, `erosion_task`, `vegetation_task`, `landuse_task`, `effluent_plume_task`, `coastal_outfall_task`, `pipeline_corridor_task`.
    *   `THEME_TASKS` (dict): Registry mapping theme strings to their Celery task functions.
    *   `ACTIVE_THEMES` (set): Controls which themes are actually dispatched during an analysis run (`rainfall`, `landuse`, `effluent_plume`, `coastal_outfall`, `pipeline_corridor`).
    *   `dispatch_all_themes(...) -> list`: Fires off `apply_async` for all requested (and active) themes into the `gee_tasks` queue.

### `workers/tasks/enrichment_tasks.py`
### `workers/tasks/enrichment_tasks.py`
*   **One-line purpose**: Aggregates all completed theme results, computes the final risk score, and triggers alerts.
*   **Type**: Celery Task Module.
*   **Classes/Functions**:
    *   `_publish_event`: Helper to publish raw JSON to Redis SSE channels.
    *   `compute_risk_score_task(run_id) -> dict`: Triggered automatically when `_check_run_complete` detects all dispatched themes are done. Steps:
        1. Loads AOI and all `ThemeResult` rows.
        2. Calls `EnrichmentService` (e.g. WorldPop for floods).
        3. Calls `CrossThemeCorrelator.evaluate()` for compound insights.
        4. Calls `RiskEngine.compute()` to aggregate final scores (including new `water_sanitation_pressure` and `infrastructure_integrity` sub-indices).
        5. Persists the final `RiskScore` to DB.
        6. Emits `risk_score` and `analysis_complete` SSE events via Redis.
        7. Triggers `evaluate_alerts_task` for threshold alerting.

### `workers/tasks/alert_tasks.py`
*   **One-line purpose**: Evaluates alerts, sends email notifications, and manages scheduled re-analyses and tile cleanup.
*   **Type**: Task Module & Cron Handlers.
*   **Functions & Signatures**:
    *   `evaluate_alerts_task(run_id: str) -> dict` (`alert_tasks` queue): Evaluates alert thresholds for completed runs using the `AlertEngine`. If alerts are triggered and `settings.ENABLE_EMAIL_ALERTS` is true, dispatches email tasks.
    *   `dispatch_alert_email_task(alert_id: str) -> dict` (`alert_tasks` queue): Sends an email notification via SendGrid and marks the alert as sent.
    *   `scheduled_reanalysis(triggered_by: str = "schedule") -> dict` (`alert_tasks` queue): Triggered by Celery Beat every 6 hours. Runs analysis on up to 50 public AOIs.
    *   `cleanup_expired_tiles() -> dict` (`alert_tasks` queue): Maintenance task. Clears GEE tile URLs in the database that are older than 6 hours.

### `workers/tasks/report_tasks.py`
*   **One-line purpose**: Generates print-friendly HTML and PDF reports from completed analysis runs.
*   **Type**: PDF Generator Task.
*   **Functions & Signatures**:
    *   `generate_report_task(run_id: str) -> dict` (`default` queue, max 2 retries):
        1.  Loads run metadata, theme results, and risk scores.
        2.  Generates report HTML content using `_build_html`.
        3.  Compiles the HTML into a PDF file using WeasyPrint.
        4.  Saves the PDF to local storage: `/tmp/gcaip_reports/gcaip_report_{run_id}.pdf`.
    *   `_build_html(run, themes, risk) -> str`: Formats report data into a clean, print-friendly HTML template.
# FastAPI Route Layers & API Endpoints

FastAPI acts as the platform entry point, handling incoming requests and streaming real-time updates to clients using Server-Sent Events (SSE). This section details the API routes and dependencies.

---

## 1. Route Dependencies

### `api/deps.py`
*   **One-line purpose**: Defines FastAPI dependencies for database sessions and Redis connections.
*   **Type**: Dependency Injection Module.
*   **Functions & Signatures**:
    *   `get_db() -> AsyncGenerator[AsyncSession, None]`: Async generator yielding database sessions. Managed in `db/session.py`.
    *   `get_redis() -> AsyncGenerator[aioredis.Redis, None]`: Yields an async Redis connection using `settings.REDIS_URL`, configured with `decode_responses=True`. Closes the connection on cleanup.

---

## 2. API v1 Endpoints

### `api/v1/health.py`
*   **One-line purpose**: System health check endpoint.
*   **HTTP Route**: `GET /api/v1/health`
*   **Logic Flow**:
    1.  Tests database connectivity by running a simple query: `SELECT 1`.
    2.  Pings Redis using the active connection.
    3.  Runs a lightweight test connection in Google Earth Engine (`test_connection`).
    4.  Returns status `ok` (latency in ms) if all checks pass, otherwise returns `degraded`.

### `api/v1/aoi.py`
*   **One-line purpose**: Manages Area of Interest (AOI) boundary creations and configurations.
*   **HTTP Routes**:
    *   `POST /api/v1/aoi` (creates a new AOI boundary):
        1.  Converts the input GeoJSON to a Shapely geometry using `_geojson_to_shape`.
        2.  Enforces max size limits (defaults to `500 km²` for anonymous users).
        3.  Runs a reverse geocode lookup (OpenStreetMap Nominatim) using the centroid coordinates to fetch admin metadata (country code, state, county).
        4.  Saves the boundary geometry and metadata to the database.
    *   `GET /api/v1/aoi/{aoi_id}` (fetches a single AOI by ID).
    *   `GET /api/v1/aoi` (lists AOI boundaries, paginated, sorted by creation date).
    *   `DELETE /api/v1/aoi/{aoi_id}` (deletes an AOI boundary).
*   **Schemas**:
    *   `AOICreateRequest`: GeoJSON data and name.
    *   `AOIResponse`: Returns the boundary ID, name, area, admin metadata, and GeoJSON coordinates.

### `api/v1/analyze.py`
### `api/v1/analyze.py`
*   **One-line purpose**: FastAPI router for triggering analysis jobs and streaming results via SSE.
*   **Type**: API Route Layer.
*   **Endpoints**:
    *   `POST /analyze`: Dispatches a background Celery analysis run via `AnalysisOrchestrator.dispatch_async`. Returns `job_id` and `sse_url`.
    *   `GET /analyze/{run_id}/status`: Polling fallback endpoint yielding current run and theme statuses.
    *   `GET /analyze/{run_id}/stream`: Main Server-Sent Events (SSE) endpoint. Connects to Redis pub/sub to stream `theme_complete`, `theme_error`, `risk_score`, and `analysis_complete` events in real-time. Includes deduplication, keepalive (15s), and DB fallback polling (15s) for reliability in case of Redis subscription race conditions. Subscribes *before* initial DB read to ensure no pub/sub messages are lost.
    *   `GET /analyze/{run_id}/results`: Fetches the complete run data, theme results, cross insights, and composite risk score after completion. Returns `FullResultsResponse` schema (which includes `result_id` in `ThemeResultSchema`).

### `api/v1/themes.py`
### `api/v1/themes.py`
*   **One-line purpose**: API for historical theme data, tile URL retrieval, and external spatial queries (e.g. Overpass).
*   **Type**: API Route Layer.
*   **Endpoints**:
    *   `GET /pipelines/search`: Proxies a spatial bounding box query to OpenStreetMap via `OverpassClient` to retrieve pipeline vector geometries (`min_lon`, `min_lat`, `max_lon`, `max_lat`).
    *   `GET /themes/{theme}/history/{aoi_id}`: Queries the TimescaleDB continuous aggregate (`metric_daily`) to return historical time-series data (value, confidence, min/max) for chart rendering.
    *   `GET /themes/{theme}/tile_url/{result_id}`: Retrieves the temporary map tile URL for a given theme result. If the URL is expired (>6h), instructs the client that it needs re-rendering.
    *   `_theme_default_unit(theme)`: Helper to map themes to units (now supporting 10 themes, including `km²` for effluent/coastal outfall and `m` for pipeline corridors).

### `api/v1/timeseries.py`
*   **One-line purpose**: Returns time-series data for dashboard charts.
*   **HTTP Route**: `GET /api/v1/timeseries/{aoi_id}`
*   **Logic Flow**:
    1.  Queries daily metrics from the continuous aggregate table (`metric_daily`) for the specified AOI.
    2.  Filters results by themes, parameters, and time windows.
    3.  Groups the records by theme for frontend chart consumption (Recharts).

### `api/v1/alerts.py`
*   **One-line purpose**: Retrieves and resolves triggered alerts.
*   **HTTP Routes**:
    *   `GET /api/v1/alerts`: Returns triggered alerts. Supports filtering by AOI, status, and severity.
    *   `GET /api/v1/alerts/{alert_id}`: Fetches an alert by ID.
    *   `POST /api/v1/alerts/{alert_id}/resolve`: Resolves an active alert, updating the status and setting the resolution timestamp.

### `api/v1/reports.py`
*   **One-line purpose**: Manages PDF report generation tasks.
*   **HTTP Routes**:
    *   `POST /api/v1/reports/{run_id}`: Triggers a report generation background task. Returns a task ID to poll.
    *   `GET /api/v1/reports/status/{task_id}`: Returns report generation task status.
# React Frontend Store & SSE Hooks

The frontend is a React application built with TypeScript, TailwindCSS, Vite, MapLibre GL for map visualizations, Recharts for charts, and Zustand for state management. This section details the store and data flow.

---

## 1. State Management Store

### `src/store/analysisStore.ts`
*   **One-line purpose**: Stores selection boundaries, running status, layer visibility, and SSE results.
*   **Type**: Zustand Store.
*   **State Fields**:
    *   `selectedAOI`: Active geocoded AOI boundary (`AOI | null`).
    *   `drawnGeoJSON`: Active drawn shape coordinates (`GeoJSON.Feature | null`).
    *   `activeRunId`: Running analysis job ID (`string | null`).
    *   `isAnalyzing`: Compute status indicator.
    *   `themeResults`: Dictionary mapping theme IDs to results (`ThemeResult`).
    *   `riskScore`: Composite risk scores (`RiskScore | null`).
    *   `selectedTheme`: Active theme selection.
    *   `mapLayerVisible`: Map layer visibility toggle states.
    *   `error`: Active error message details.
    *   `isDrawing`: Boundary drawing mode state.
    *   `interactionMode`: Map interaction mode (`navigate`\|`point`\|`rectangle`).
    *   `selectedPresetId` / `selectedPresetZone`: Reference boundaries.
*   **Key Mutator Actions**:
    *   `startAnalysis(runId)`: Sets the running state, clears previous results, and resets errors.
    *   `setThemeResult(theme, result)`: Appends completed theme results and updates default layer visibility.
    *   `setRiskScore(score)`: Stores composite scores.
    *   `completeAnalysis()`: Resets compute status indicator.
    *   `toggleLayerVisibility(theme)`: Toggles map layer display.
    *   `reset()`: Resets state back to initial values.

---

## 2. Server-Sent Events Consumer Hook

### `src/hooks/useSSEStream.ts`
*   **One-line purpose**: Subscribes to the backend SSE endpoint and commits updates to the Zustand store.
*   **Type**: React Hook.
*   **Logic Flow**:
    1.  Listens for active `runId` states.
    2.  Creates a native `EventSource` connection pointing to `${API_BASE}/analyze/${runId}/stream`.
    3.  Attaches an `onmessage` handler to parse incoming JSON payloads.
    4.  Processes events:
        *   `connected`: Confirms connection.
        *   `theme_complete` / `theme_error`: Calls `setThemeResult` with the updated status.
        *   `risk_score`: Calls `setRiskScore`.
        *   `analysis_complete`: Calls `completeAnalysis` and closes the stream.
        *   `error`: Calls `setError` and closes the stream.
    5.  Implements auto-reconnect behavior in `onerror`. If the connection is fully terminated (`CLOSED`), sets a fatal error.
    6.  Cleans up and closes the connection when the component unmounts or the `runId` changes.

---

## 3. Frontend Types Reference

### `src/types/theme.ts`
*   **One-line purpose**: TypeScript type interfaces for GCAIP entities.
*   **Key Interfaces**:
    *   `ThemeId`: Literal union (`'flood' | 'rainfall' | 'reservoir' | 'mangrove' | 'erosion' | 'vegetation' | 'landuse' | 'effluent_plume' | 'coastal_outfall' | 'pipeline_corridor'`).
    *   `ThemeResult`: Maps directly to the backend's `ThemeResult` JSON representation (metric value, unit, label, stats, confidence, etc.).
    *   `EnrichedContext`: Defines the geocoded population and infrastructure count fields.
    *   `RiskScore`: Defines the overall score and the list of cross-theme insights.
    *   `Alert`: Defines alert event fields.

---

## 4. Key Component Structure

### `GlobeView.tsx`
*   **Purpose**: Main MapLibre GL map viewport.
*   **Key Logic**:
    *   Renders the map context.
    *   Displays drawn shapes and selected boundaries.
    *   Loads GEE map tile layers (`ThemeLayerManager`) based on visibility configurations.

### `DrawControl.tsx`
*   **Purpose**: Drawing tools interface.
*   **Key Logic**:
    *   Provides rectangle and point drawing tools.
    *   Integrates with Mapbox Draw to capture coordinate boundaries.

### `ThemeCard.tsx`
*   **Purpose**: Displays the status and metrics for individual analysis themes.
*   **Key Logic**:
    *   Shows loading skeletons while analysis is running.
    *   Renders metrics, units, and data sources on completion.
    *   Displays error states (with classification details).

### `ValidationPanel.tsx`
*   **Purpose**: Sidebar UI for managing analysis runs and displaying results.
*   **Key Logic**:
    *   Triggers new analyses and monitors progress.
    *   Displays the overall risk score, geocoded population metrics, and active alerts.
    *   Renders cross-theme insights and recommended actions.
## 7. Frontend Application

The React SPA built with Vite, TypeScript, and TailwindCSS.

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/hooks/useSSEStream.ts`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `useSSEStream` (React Application Root)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/store/analysisStore.ts`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `useAnalysisStore` (React Application Root)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/api/analysis.ts`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `AnalyzeRequestBody` (TypeScript interface)
    *   `FullResults` (TypeScript interface)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/api/aoi.ts`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/api/client.ts`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `api` (React Application Root)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/api/pipelines.ts`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `PipelineSearchParams` (TypeScript interface)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/components/analysis/AnalysisPanel.tsx`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `AnalysisPanel` (React Application Root)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/components/analysis/CrossInsightsList.tsx`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `CrossInsightsList` (React Application Root)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/components/analysis/RiskScoreHeader.tsx`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `RiskScoreHeader` (React Application Root)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/components/analysis/ValidationPanel.tsx`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `ValidationPanel` (React Application Root)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/components/globe/DrawControl.tsx`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `DrawControl` (React Application Root)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/components/globe/GlobeView.tsx`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `GlobeView` (React Application Root)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/components/globe/TestZonesPanel.tsx`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `TestZonesPanel` (React Application Root)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/components/globe/ThemeLayerManager.tsx`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `ThemeLayerManager` (React Application Root)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/components/shared/TopBar.tsx`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `TopBar` (React Application Root)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/components/shared/WelcomeOverlay.tsx`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `WelcomeOverlay` (React Application Root)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/components/themes/ThemeCard.tsx`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `ThemeCard` (React Application Root)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/components/themes/ThemeCardSkeleton.tsx`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `ThemeCardSkeleton` (React Application Root)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/components/themes/ThemeDetailPanel.tsx`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `ThemeDetailPanel` (React Application Root)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/components/themes/themeIcons.ts`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `themeIcon` (React Application Root)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/types/theme.ts`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `ThemeId` (TypeScript type)
    *   `ThemeStatus` (TypeScript type)
    *   `Severity` (TypeScript type)
    *   `RiskLabel` (TypeScript type)
    *   `VisParams` (TypeScript interface)
    *   `ThemeResult` (TypeScript interface)
    *   `EnrichedContext` (TypeScript interface)
    *   `AssetTrajectory` (TypeScript interface)
    *   `CrossInsight` (TypeScript interface)
    *   `RiskScore` (TypeScript interface)
    *   `AOI` (TypeScript interface)
    *   `AnalyzeResponse` (TypeScript interface)
    *   `RunStatus` (TypeScript interface)
    *   `Alert` (TypeScript interface)
    *   `SSEEvent` (TypeScript type)
    *   `THEME_LABELS` (React Application Root)
    *   `THEME_ORDER` (React Application Root)
    *   `ACTIVE_THEMES` (React Application Root)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/App.tsx`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `App` (React Application Root)

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/main.tsx`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/vite-env.d.ts`
*   **One-line purpose**: <reference types="vite/client" />
*   **Type**: React Application Root

### `d:/Projects/GCAIP_Project_v2/gcaip/gcaip-frontend/src/data/presetZones.ts`
*   **One-line purpose**: Frontend component/module.
*   **Type**: React Application Root
*   **Classes/Functions**:
    *   `RainfallExpected` (TypeScript interface)
    *   `LanduseExpected` (TypeScript interface)
    *   `EffluentPlumeExpected` (TypeScript interface)
    *   `CoastalOutfallExpected` (TypeScript interface)
    *   `PipelineCorridorExpected` (TypeScript interface)
    *   `PresetExpected` (TypeScript interface)
    *   `ValidationTier` (TypeScript type)
    *   `PresetZone` (TypeScript interface)
    *   `PRESET_ZONES` (React Application Root)

## 8. Configuration & Migrations

### `config.py`
*   **One-line purpose**: Application-wide settings parsed from `.env` using Pydantic BaseSettings.
*   **Type**: Configuration
*   **Key settings**:
    *   `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`
    *   `GEE_TIMEOUT_SECONDS` (120), `GEE_MAX_RETRIES` (3), `CELERY_TASK_SOFT_TIME_LIMIT` (600s).
    *   Feature flags: `ENABLE_SCHEDULED_ANALYSIS`, `ENABLE_EMAIL_ALERTS`.

### `alembic/versions/001_initial.py`
*   **One-line purpose**: Initial baseline schema creation.
*   **Type**: Database Migration
*   **Action**: Sets up `aois`, `analysis_runs`, `theme_results`, and `alerts` tables. Uses PostGIS `Geometry` types for AOI polygons.

### `alembic/versions/002_schema_drift_fixes.py`
*   **One-line purpose**: Synchronizes the database schema with the latest SQLAlchemy models.
*   **Type**: Database Migration
*   **Action**: 
    *   Adds `error_class` (VARCHAR 50) to `theme_results` table.
    *   Creates the new `risk_scores` table (id, run_id, aoi_id, overall_score, flood_risk, erosion_risk, water_stress, vegetation_health, landuse_pressure, water_sanitation_pressure, infrastructure_integrity, cross_insights, population_in_aoi, population_at_risk, scored_at).
