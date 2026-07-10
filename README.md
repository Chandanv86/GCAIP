# GCAIP — Geospatial Climate Adaptation Intelligence Platform

Converts free satellite data into actionable climate intelligence.
Click anywhere on Earth → get flood extent, rainfall anomaly, reservoir
status, mangrove health, coastal erosion rate, vegetation buffer health,
and land use change — enriched with population and infrastructure impact,
streamed back in real time via SSE.

## Architecture

GEE does ALL satellite processing (server-side, Python API). FastAPI is
orchestration only. Celery workers run all 7 GEE theme processors in
parallel; results stream to the frontend via Server-Sent Events as each
theme completes. Every result carries `confidence` and `data_age_hours`.

```
gcaip-backend/      FastAPI + Celery + GEE processors + PostGIS/TimescaleDB
gcaip-frontend/     React 18 + TypeScript + MapLibre GL JS globe + SSE
```

## Build Status

- [X] docker-compose.yml (PostgreSQL+PostGIS+TimescaleDB + Redis)
- [X] Database migrations (Alembic) — all 5 tables + TimescaleDB hypertable
- [X] GEE authentication (`gee/client.py`)
- [X] All 7 GEE processors (flood, rainfall, reservoir, mangrove, erosion, vegetation, landuse)
- [X] Celery app + theme tasks (parallel dispatch, one task per theme)
- [X] AOI endpoint (POST /api/v1/aoi)
- [X] Analyze endpoint (POST /api/v1/analyze)
- [X] SSE stream endpoint (GET /api/v1/analyze/{run_id}/stream)
- [X] Enrichment service (WorldPop + OSM Overpass)
- [X] Risk score engine (5-component weighted composite)
- [X] Cross-theme correlation engine (6 compound-risk rules)
- [X] Alert engine + threshold evaluation
- [X] Frontend: Globe + click-to-AOI + polygon draw
- [X] Frontend: SSE loader + progressive theme cards
- [X] Frontend: GEE tile overlays on map
- [X] Alert dispatch (Celery Beat scheduled re-analysis + SendGrid)
- [X] PDF report generator (WeasyPrint)

## ⚠️ Action Required Before Production

1. **GMW v3 asset path** (`gee/processors/mangrove.py`) — the path
   `projects/mangrovecapital/assets/GMW/v3/GMW_v3_2020_vec` was not in the
   pre-confirmed asset list. **Verify this in the GEE Code Editor catalog
   search before deploying** — GMW has changed hosting organizations
   before. If wrong, the mangrove processor will fail gracefully (caught
   exception → `gain_ha`/`loss_ha` = 0, `gmw_baseline_used: false`) but you
   lose the baseline comparison.
2. **GEE service account** — create one at
   https://developers.google.com/earth-engine/guides/service_account,
   download the JSON key to `gcaip-backend/credentials/gee-service-account.json`,
   set `GEE_SERVICE_ACCOUNT` in `.env`.
3. **WorldPop REST endpoint** — the exact REST query shape in
   `integrations/worldpop.py._fetch_rest()` is a best-effort implementation
   against WorldPop's documented API surface. It has a GEE raster fallback
   (`WorldPop/GP/100m/pop`) that will work regardless, so enrichment never
   hard-fails, but verify the REST path against current WorldPop docs for
   best latency.
4. **Overpass API rate limits** — the public `overpass-api.de` instance
   throttles aggressively under load. For production scale, run your own
   Overpass instance or use a paid provider (e.g., Geofabrik extracts +
   self-hosted Overpass).

## Quick Start

### 1. Prerequisites

Ensure you have the following installed on your system:

- **Docker & Docker Compose**
- **Python 3.11+** (if running locally)
- **Node.js 18+ & npm** (if running frontend locally)

> [!IMPORTANT]
> **Docker networking: `localhost` ≠ `redis` inside containers.**
> When the API, worker, and beat containers run inside Docker Compose, they cannot reach
> Redis via `localhost` — they must use the Docker service name `redis`.
> The `docker-compose.yml` already sets `REDIS_URL`, `CELERY_BROKER_URL`, and
> `CELERY_RESULT_BACKEND` to `redis://redis:6379/...` for all services.
> **Never override these with `localhost` values inside containers.**
> For **bare-metal development** (Option B), `localhost:6379` is correct because the app
> runs directly on the host and connects to the Docker-exposed port.
>
> **Startup health checks:** Both the FastAPI process and the Celery worker ping Redis
> at startup. If Redis is unreachable, you will see a clear log line:
> `gcaip.startup.redis_unavailable` with actionable hints — not a raw connection error.
> A successful connection logs: `gcaip.startup.redis_ok url=redis://...`

---

### 2. Google Earth Engine (GEE) Credentials

To enable satellite processing, you must configure a GEE service account:

1. Download your service account JSON key and place it inside `gcaip-backend/credentials/`.
2. Ensure the filename matches `africa-analysis45678-89989fd43a20.json` (or update it in `.env` and `docker-compose.yml` to match your custom filename).
3. Open `gcaip-backend/.env` and update the GEE variables:
   ```env
   GEE_SERVICE_ACCOUNT=gee-water-platform@africa-analysis45678.iam.gserviceaccount.com
   GEE_CREDENTIALS_PATH=credentials/africa-analysis45678-89989fd43a20.json
   GEE_PROJECT=africa-analysis45678
   ```

---

### 3. How to Run (Choose Option A or Option B)

#### Option A: Full Docker Compose Mode (Easiest)

This runs the entire backend suite (PostgreSQL/TimescaleDB, Redis, FastAPI, Celery Worker, and Celery Beat) in Docker.

1. Navigate to the backend directory and spin up all containers:
   ```bash
   cd gcaip-backend
   docker compose up --build -d
   ```
2. Run database migrations inside the active API container (using the name shadowing helper script):
   ```bash
   docker compose exec api python run_migrations.py
   ```
3. Check logs to verify service initialization:
   ```bash
   docker compose logs -f api worker
   ```

---

#### Option B: Hybrid Mode (Fast local python execution + DB/Redis in Docker)

Best for active backend code changes, debugging, and live reloading.

1. **Start Database and Redis containers**:
   ```bash
   cd gcaip-backend
   docker compose up -d db redis
   ```

2. **Set up Python Virtual Environment & Install Dependencies**:
   - **On Windows**:
     ```powershell
     python -m venv venv
     .\venv\Scripts\activate
     pip install -r requirements.txt
     ```
   - **On macOS/Linux**:
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     pip install -r requirements.txt
     ```

3. **Run database migrations**:
   ```bash
   # Ensure your virtual environment is active in your terminal
   alembic upgrade head
   ```

4. **Start the FastAPI server**:
   - **On Windows (PowerShell)**:
     ```powershell
     $env:PYTHONDONTWRITEBYTECODE=1
     uvicorn main:app --reload --port 8000
     ```
   - **On macOS/Linux**:
     ```bash
     export PYTHONDONTWRITEBYTECODE=1
     uvicorn main:app --reload --port 8000
     ```

5. **Start the Celery worker** (in a separate terminal with venv active):
   - **On Windows (PowerShell)** (requires `-P solo` to prevent `WinError 5` permission errors):
     ```powershell
     cd gcaip-backend
     .\venv\Scripts\activate
     $env:PYTHONDONTWRITEBYTECODE=1
     celery -A workers.celery_app worker --loglevel=info -P solo -Q default,gee_tasks,enrichment_tasks,alert_tasks
     ```
   - **On macOS/Linux**:
     ```bash
     cd gcaip-backend
     source venv/bin/activate
     export PYTHONDONTWRITEBYTECODE=1
     celery -A workers.celery_app worker --loglevel=info --concurrency=2 -Q default,gee_tasks,enrichment_tasks,alert_tasks
     ```

6. **Start Celery Beat** (only needed for scheduled alerts, in a separate terminal with venv active):
   - **On Windows**:
     ```powershell
     cd gcaip-backend
     .\venv\Scripts\activate
     celery -A workers.celery_app beat --loglevel=info
     ```
   - **On macOS/Linux**:
     ```bash
     cd gcaip-backend
     source venv/bin/activate
     celery -A workers.celery_app beat --loglevel=info
     ```

---

### 4. Running the Frontend

Your frontend is served by Vite on port `5173`.

1. Navigate to the frontend directory and install dependencies:
   ```bash
   cd gcaip-frontend
   npm install
   ```
2. Start the development server:
   ```bash
   npm run dev
   ```

---

### 5. Verification & Access URLs

- **Web App UI**: [http://localhost:5173](http://localhost:5173)
- **API Swagger Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **System Health Status Check**: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health) (verifies database, Redis, and GEE credentials validation)

## Non-Negotiables Implemented

1. **GEE is the EO engine** — zero GDAL pipelines, zero raw imagery downloads.
   `gee/client.py` is the single GEE entry point; `backend never downloads raw imagery` is enforced by design (only `getMapId()` tile URLs and
   `reduceRegion()` stats cross the GEE boundary).
2. **SAR first** — flood, reservoir, and erosion processors use Sentinel-1
   GRD as primary; Sentinel-2 (vegetation, mangrove, landuse) explicitly
   falls back gracefully when cloud cover blocks optical data (erosion
   processor has an NDWI fallback path; flood widens the orbit pass filter).
3. **Confidence + data_age_hours on every result** — enforced via the
   `ThemeResult` dataclass in `gee/processors/base.py`; `error_result()`
   classmethod guarantees these fields are never null even on failure.
4. **SSE, not polling** — `api/v1/analyze.py::stream_results` subscribes to
   a Redis pub/sub channel per run; Celery tasks publish to it as each
   theme completes. Frontend uses native `EventSource`
   (`hooks/useSSEStream.ts`).
5. **Celery for all GEE calls** — `workers/tasks/theme_tasks.py`; no GEE
   call exists in any FastAPI route handler.
6. **Enrichment is mandatory for flood/erosion** — `services/enrichment.py`
   is invoked automatically in `compute_risk_score_task` once an active
   flood or negative-EPR erosion result lands.
7. **6-hour Redis cache** — `services/orchestrator.py::_make_cache_key`
   hashes AOI geometry + date range; `workers/tasks/theme_tasks.py::_run_theme`
   checks this cache before invoking any processor.

## What's Next (Phase 2, scaffolded but not wired to a UI)

- Email alert dispatch is implemented (`integrations/sendgrid_client.py`,
  `workers/tasks/alert_tasks.py::dispatch_email_alert_task`) but
  `ENABLE_EMAIL_ALERTS=false` by default — flip the flag and add a user
  email field to `AOI`/`User` to activate.
- GloFAS CDS API integration is referenced in config but not implemented —
  `ENABLE_GLOFAS=false`. Useful for upstream river discharge as a 5th
  flood-risk signal alongside SAR.
- User authentication is stubbed (`models/user.py` exists, no auth routes
  yet) — AOIs are currently anonymous/public.
