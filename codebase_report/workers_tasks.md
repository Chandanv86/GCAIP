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
*   **One-line purpose**: Runs GEE theme processors, saves results, and publishes updates to Redis.
*   **Type**: Task Module.
*   **Functions & Signatures**:
    *   `_get_sync_session()`: Creates a synchronous SQLAlchemy session, swapping the database driver to `psycopg2`.
    *   `_publish_theme_event(run_id: str, theme: str, result_dict: dict)`: Publishes task updates (event type `theme_complete` or `theme_error`) to a Redis channel (`gcaip:sse:{run_id}`).
    *   `_store_theme_result(run_id: str, theme: str, result)`: Updates or inserts the `ThemeResult` record in the database.
    *   `_check_run_complete(run_id: str) -> bool`: Checks if all theme tasks for a run are finished (complete/failed/skipped) and triggers the risk scoring task if complete.
    *   `_run_theme(processor_cls, theme: str, run_id: str, aoi_geojson: dict, date_range: tuple, cache_key: str | None = None) -> dict`: Shared logic for GEE tasks. Checks for cached results in Redis first. Otherwise, runs the GEE processor, caches the result if confidence is `>= 0.4`, saves the result to the DB, and publishes an update event.
    *   `dispatch_all_themes(run_id: str, aoi_geojson: dict, date_range: tuple[str, str], themes: list[str] | None = None, cache_key: str | None = None) -> list`: Dispatches parallel theme tasks based on active and requested configurations.
*   **Registered Tasks** (max 2 retries, `gee_tasks` queue):
    *   `flood_task` (Theme 1: `FloodProcessor`)
    *   `rainfall_task` (Theme 2: `RainfallProcessor`)
    *   `reservoir_task` (Theme 3: `ReservoirProcessor`)
    *   `mangrove_task` (Theme 4: `MangroveProcessor`)
    *   `erosion_task` (Theme 5: `ErosionProcessor`)
    *   `vegetation_task` (Theme 6: `VegetationProcessor`)
    *   `landuse_task` (Theme 7: `LandUseProcessor`)
    *   `effluent_plume_task` (Theme 8: `EffluentPlumeProcessor`)
    *   `coastal_outfall_task` (Theme 9: `CoastalOutfallProcessor`)
    *   `pipeline_corridor_task` (Theme 10: `PipelineCorridorProcessor`)

### `workers/tasks/enrichment_tasks.py`
*   **One-line purpose**: Runs WorldPop and OSM enrichment, evaluates cross-theme insights, and computes risk scores.
*   **Type**: Task Module.
*   **Functions & Signatures**:
    *   `compute_risk_score_task(run_id: str) -> dict` (runs in `enrichment_tasks` queue, max 2 retries):
        1.  Loads all completed theme results for a run from the database.
        2.  Extracts the AOI geometry and runs geocoding/infrastructure enrichment.
        3.  Runs the `CrossThemeCorrelator` to evaluate compound risks and generate cross-theme insights.
        4.  Runs the `RiskEngine` to compute the overall risk score.
        5.  Saves the `RiskScore` record to the database.
        6.  Marks the run as complete and records the completion timestamp.
        7.  Publishes `risk_score` and `analysis_complete` events to the Redis channel.
        8.  Triggers the `evaluate_alerts_task` background task.

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
