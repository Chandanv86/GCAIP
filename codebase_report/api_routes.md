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
*   **One-line purpose**: Triggers analyses and streams results via SSE.
*   **HTTP Routes**:
    *   `POST /api/v1/analyze` (triggers a run):
        1.  Verifies the requested AOI exists.
        2.  Converts PostGIS spatial geometry to GeoJSON coordinates.
        3.  Dispatches the analysis run asynchronously via `AnalysisOrchestrator.dispatch_async`.
        4.  Returns the analysis run ID, status, and the Server-Sent Events stream URL.
    *   `GET /api/v1/analyze/{run_id}/status` (polling fallback).
    *   `GET /api/v1/analyze/{run_id}/stream` (primary results stream):
        1.  Fetches any already-completed theme results from the database (important for eager executions or clients reconnecting).
        2.  Streams completed results immediately.
        3.  If any tasks are still running, subscribes to the Redis channel `gcaip:sse:{run_id}`.
        4.  Enters a message-receive loop, yielding results as they are published by workers.
        5.  Sends a `keepalive` comment every 15 seconds to prevent connection dropouts.
        6.  Closes the connection once `analysis_complete` or an `error` event is received.
    *   `GET /api/v1/analyze/{run_id}/results` (retrieves full results for completed runs).
*   **SSE Event Payloads**:
    *   `connected`: Connection confirmation.
    *   `theme_complete` / `theme_error`: Returns individual theme results or error details.
    *   `risk_score`: Returns overall risk score and cross-theme insights.
    *   `analysis_complete`: Signals the analysis run is finished.
    *   `error`: Returns fatal execution details.

### `api/v1/themes.py`
*   **One-line purpose**: Retrieves theme aggregates and handles map tile refreshes.
*   **HTTP Routes**:
    *   `GET /api/v1/pipelines/search`: Queries OSM Overpass for pipeline centerline geometries within a bounding box.
    *   `GET /api/v1/themes/{theme}/history/{aoi_id}`: Queries daily historical metrics from TimescaleDB (`metric_daily`). Supports filtering by date range (period) and parameter variables.
    *   `GET /api/v1/themes/{theme}/tile_url/{result_id}`: Returns map tile URLs. If the tile has expired (> 6 hours), triggers a refresh.

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
