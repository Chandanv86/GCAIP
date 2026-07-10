# Analytical Backend Services & Integrations

This section describes the services that coordinate analysis runs, calculate composite risk scores, evaluate alerts, query external database APIs, and project erosion timelines.

---

## 1. Core Services

### `services/orchestrator.py`
*   **One-line purpose**: Manages analysis runs, pre-creates results rows, and dispatches parallel Celery tasks.
*   **Type**: Run Controller.
*   **Functions & Signatures**:
    *   `async def dispatch_async(self, db: AsyncSession, aoi_id: str, aoi_geojson: dict, date_range: tuple[str, str] | None = None, themes: list[str] | None = None, triggered_by: str = "user") -> str`: Handles requests from the FastAPI layer. Creates an `AnalysisRun` row in the database, inserts `ThemeResult` placeholders for the requested themes, commits the transaction, and dispatches Celery tasks.
    *   `def dispatch(self, aoi_id: str, aoi_geojson: dict, date_range: tuple[str, str] | None = None, themes: list[str] | None = None, triggered_by: str = "schedule") -> str`: Sync alternative used by Celery Beat scheduling. Opens a sync database connection (swaps database driver to `psycopg2`), inserts run rows, and triggers task dispatches.
    *   `_default_date_range() -> tuple[str, str]`: Computes default time window (last 30 days).
    *   `_make_cache_key(aoi_geojson: dict, start: str, end: str) -> str`: Generates a deterministic hash from the geometry and date strings. Used for GEE tile caching.
*   **Constants & Thresholds**:
    *   Default analysis themes (`ALL_THEMES`): `["rainfall", "landuse", "effluent_plume", "coastal_outfall", "pipeline_corridor"]`.

### `services/risk_engine.py`
*   **One-line purpose**: Calculates a composite climate risk score (0-100) from completed theme results.
*   **Type**: Analytical Engine.
*   **Functions & Logic Flow**:
    *   `compute(results_by_theme: dict) -> RiskScore`:
        1.  Calls `_water_stress_index` using rainfall, effluent plume, and coastal outfall metrics.
        2.  Calls `_landuse_pressure_index` using land use and pipeline corridor metrics.
        3.  Computes the overall score as a weighted average: `overall = (water_stress * 0.50) + (landuse_pressure * 0.50)`.
        4.  Calculates pollution and infrastructure risk scores (logged but not yet factored into the overall score).
        5.  Maps the overall score to a classification label (e.g. LOW, CRITICAL).
*   **Constants, Weights & Thresholds**:
    *   Active Weights: `water_stress` = `0.50`, `landuse` = `0.50` (Disabled themes `flood`, `erosion`, `vegetation` are omitted).
    *   Risk categories: `[0-25]` LOW, `[26-50]` MODERATE, `[51-75]` HIGH, `[76-100]` CRITICAL.
    *   `_water_stress_index`: Accumulates points for rainfall anomalies and reservoir levels. Plumes and coastal outfalls contribute a 15% weight to this metric.
    *   `_landuse_pressure_index`: Runoff increases `>20%` contribute 60 points, and the remaining 40 points scale with the changed area (capped at 500 ha). Encroachments add up to a 20 point penalty.

### `services/alert_engine.py`
*   **One-line purpose**: Evaluates calculated metrics against threshold rules to trigger alerts.
*   **Type**: Rule Engine.
*   **Functions & Logic Flow**:
    *   `evaluate(aoi_id: str, run_id: str, theme_results: dict, session) -> list`:
        1.  Loops through active themes (rainfall, effluent plume, coastal outfall, pipeline corridor).
        2.  Skips checks if the GEE result confidence is below 40%.
        3.  Checks thresholds for each rule.
        4.  Verifies the confidence is above the rule's minimum threshold.
        5.  Generates a deduplication key (`{aoi_id}:{alert_type}:{YYYY-MM-DD}`) and checks if an alert was already sent today.
        6.  Formats alert text templates and creates an `Alert` database record.
*   **Alert Rules & Thresholds**:
    *   `extreme_rainfall`: Triggered if `spi_7 >= 2.0` (min confidence 70%, WATCH).
    *   `effluent_plume_detected`: Triggered if `plume_extent_km2 >= 0.5` (min confidence 60%, WATCH).
    *   `thermal_plume_active`: Triggered if `thermal_plume_flag` is True (min confidence 60%, WATCH).
    *   `spm_spike`: Triggered if `spm_mean >= 20.0` mg/L (min confidence 60%, WATCH).
    *   `corridor_encroachment`: Triggered if `encroachment_ha >= 5.0` (min confidence 70%, WARNING).
    *   `corridor_disturbance`: Triggered if `disturbed_corridor_length_m >= 5000.0` (min confidence 60%, WATCH).
    *   *Disabled rules*: `flood_active` (is_active True), `spillway_risk` (HIGH/CRITICAL), `erosion_storm` (EPR < -2m/yr and wave risk HIGH), `mangrove_loss` (net change < -100 ha).

### `services/cross_theme.py`
*   **One-line purpose**: Detects compound risks when multiple hazard themes overlap.
*   **Type**: Correlation Engine.
*   **Functions & Logic Flow**:
    *   `evaluate(stats_by_theme: dict[str, dict]) -> list[CrossInsight]`:
        1.  Extracts metrics from completed GEE runs.
        2.  Applies compound rules to check for overlapping conditions.
        3.  Generates `CrossInsight` objects with severity levels and action recommendations.
        4.  Sorts insights by severity: `EMERGENCY` → `WARNING` → `WATCH` → `INFO`.
*   **Compound Rules & Recommended Actions**:
    *   *Spillway Risk*: Reservoir fill `>85%` + 7-day rainfall `>90th percentile`. Recommended Action: Notify operators, pre-position evacuation resources, monitor gates every 6 hours.
    *   *Runoff Amplification*: SPI-7 `>1.5` + landuse runoff increase `>10%`. Recommended Action: Alert watershed managers, restrict clearing, deploy barriers.
    *   *Downstream Compound Risk*: Active flood + reservoir fill `>90%`. Recommended Action: Issue warnings, activate emergency ops, evacuate within 10km.
    *   *Storm Erosion*: Erosion EPR `< -1.5` m/yr + wave risk `HIGH`. Recommended Action: Relocate beach assets immediately, restrict access, alert engineering teams.
    *   *Buffer Collapse*: Mangrove loss `>50` ha + erosion EPR `< -1.0` m/yr. Recommended Action: Prioritize mangrove restoration, install temporary wave-breaks.
    *   *Extended Inundation*: Active flood + SPI-7 `>2.0`. Recommended Action: Prepare for 72h+ inundation, stockpile clean water and medicine.
    *   *Runoff Driven Plume*: SPI-7 `>1.5` + inland plume `>0.1` km². Recommended Action: Inspect storm bypass gates and discharge points, monitor intake turbidity.
    *   *Runoff Marine Plume*: SPI-7 `>1.5` + coastal outfall SPM `>15.0` mg/L. Recommended Action: Alert port authorities, track trajectory using dispersion bearing.
    *   *Encroachment Confirmed*: Corridor encroachment `>0.0` ha + landuse tree/natural-to-built change `>0.0` ha. Recommended Action: Dispatch patrol team to inspect for unauthorized construction or clearing.

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
