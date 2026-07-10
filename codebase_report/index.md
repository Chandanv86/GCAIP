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
*   `id` (`UUID`): Primary key. Default: `gen_random_uuid()`.
*   `run_id` (`UUID`): Foreign key to `analysis_runs.id`. Index `idx_results_run`.
*   `theme` (`VARCHAR(64)`): Theme name. Index `idx_results_theme_time` (`theme`, `completed_at`).
*   `status` (`VARCHAR(32)`): pending\|running\|complete\|failed\|skipped.
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
*   *Constraint*: `UniqueConstraint("run_id", "theme", name="uq_run_theme")`.

#### Table: `risk_scores`
*   `id` (`UUID`): Primary key.
*   `run_id` (`UUID`): Foreign key to `analysis_runs.id` (Unique).
*   `aoi_id` (`UUID`): Foreign key to `aois.id`. Index `idx_risk_aoi_time` (`aoi_id`, `scored_at`).
*   `overall_score` (`DOUBLE PRECISION`): Weighted composite (0-100).
*   `overall_label` (`VARCHAR(16)`): LOW\|MODERATE\|HIGH\|CRITICAL.
*   `flood_risk` (`DOUBLE PRECISION`): Optional.
*   `erosion_risk` (`DOUBLE PRECISION`): Optional.
*   `water_stress` (`DOUBLE PRECISION`): Optional.
*   `vegetation_health` (`DOUBLE PRECISION`): Optional.
*   `landuse_pressure` (`DOUBLE PRECISION`): Optional.
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

Below are the background tasks registered in the Celery cluster configuration.

| Registered Task Name | Queue | Trigger / Schedule |
| :--- | :--- | :--- |
| `workers.tasks.theme_tasks.flood_task` | `gee_tasks` | Dispatched as part of analysis orchestrator group. |
| `workers.tasks.theme_tasks.rainfall_task` | `gee_tasks` | Dispatched as part of analysis orchestrator group. |
| `workers.tasks.theme_tasks.reservoir_task` | `gee_tasks` | Dispatched as part of analysis orchestrator group. |
| `workers.tasks.theme_tasks.mangrove_task` | `gee_tasks` | Dispatched as part of analysis orchestrator group. |
| `workers.tasks.theme_tasks.erosion_task` | `gee_tasks` | Dispatched as part of analysis orchestrator group. |
| `workers.tasks.theme_tasks.vegetation_task` | `gee_tasks` | Dispatched as part of analysis orchestrator group. |
| `workers.tasks.theme_tasks.landuse_task` | `gee_tasks` | Dispatched as part of analysis orchestrator group. |
| `workers.tasks.theme_tasks.effluent_plume_task` | `gee_tasks` | Dispatched as part of analysis orchestrator group. |
| `workers.tasks.theme_tasks.coastal_outfall_task` | `gee_tasks` | Dispatched as part of analysis orchestrator group. |
| `workers.tasks.theme_tasks.pipeline_corridor_task` | `gee_tasks` | Dispatched as part of analysis orchestrator group. |
| `workers.tasks.enrichment_tasks.compute_risk_score_task` | `enrichment_tasks` | Dispatched automatically by `_check_run_complete` when all theme results are complete. |
| `workers.tasks.alert_tasks.evaluate_alerts_task` | `alert_tasks` | Dispatched after `compute_risk_score_task` completes. |
| `workers.tasks.alert_tasks.dispatch_email_alert_task` | `alert_tasks` | Triggered if new alerts are generated and `ENABLE_EMAIL_ALERTS` is true. |
| `workers.tasks.alert_tasks.scheduled_reanalysis` | `alert_tasks` | Cron: `0 */6 * * *` (Every 6 hours) via Celery Beat. |
| `workers.tasks.alert_tasks.cleanup_expired_tiles` | `alert_tasks` | Cron: `30 */6 * * *` (Every 6 hours) via Celery Beat. |
| `workers.tasks.report_tasks.generate_report_task` | `default` | Triggered by API route request (`POST /api/v1/reports/{run_id}`). |

---

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
