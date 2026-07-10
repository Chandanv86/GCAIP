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
*   **One-line purpose**: Detects chlorophyll and turbidity plumes in inland water bodies.
*   **Type**: Active Theme Processor.
*   **Algorithms & Logic Flow**:
    1.  Loads optical imagery using a fallback cascade: Sentinel-2 (default → +15d → +30d → 60% cloud) → Landsat 8/9 (default → +30d) → Sentinel-3 OLCI.
    2.  Applies a Modified Normalized Difference Water Index (MNDWI > 0.1) to mask land pixels.
    3.  Calculates NDCI (Normalized Difference Chlorophyll Index) using S2 Bands Red-Edge/Red (B5/B4) and NDTI (Normalized Difference Turbidity Index) using Red/Green (B4/B3).
    4.  Flags plume pixels where `NDCI > 0.05` and `NDTI > 0.10` within the water mask.
    5.  Compares results with a prior-year seasonal composite baseline.
    6.  Calculates plume surface area in square kilometers.
*   **Constants & Thresholds**:
    *   `MNDWI_THRESHOLD` = `0.1`
    *   `NDCI_THRESHOLD` = `0.05`
    *   `NDTI_THRESHOLD` = `0.10`
    *   Landsat scaling multiplier = `0.0000275`, offset = `-0.2`.

### `coastal_outfall.py` (Theme 9)
*   **One-line purpose**: Characterizes marine discharge plumes and thermal anomalies at outfalls.
*   **Type**: Active Theme Processor.
*   **Algorithms & Logic Flow**:
    1.  Checks for water coverage: stops and returns "not applicable" if the AOI contains fewer than 10 water pixels (ESA WorldCover class 80).
    2.  Sets the outfall anchor point (explicit coordinates if provided, otherwise the AOI centroid).
    3.  Loads Sentinel-2 imagery with fallback and applies a SWIR1 glint filter (`B11 < 0.02`).
    4.  Calculates Suspended Particulate Matter (SPM) using red reflectance (`B4`): `SPM = (355.85 * B4) / (1 - (B4 / 0.1728))`.
    5.  Calculates CDOM (Colored Dissolved Organic Matter) index using Blue/Green ratio (`B2 / B3`).
    6.  Combines CDOM and SPM, computes a Sobel gradient, and sets the plume boundary at the 90th percentile of this gradient.
    7.  Measures plume dispersion bearing relative to the outfall anchor.
    8.  Loads Landsat thermal bands to measure sea surface temperature anomalies.
*   **Constants & Thresholds**:
    *   `GLINT_B11_THRESHOLD` = `0.02`
    *   `THERMAL_PLUME_DELTA_C` = `1.5°C` (temperature difference over ambient)
    *   SPM coefficients: `A` = `355.85`, `C` = `0.1728`.

### `pipeline_corridor.py` (Theme 10)
*   **One-line purpose**: Monitors pipeline corridors for encroachment and vegetation clearing.
*   **Type**: Active Theme Processor.
*   **Algorithms & Logic Flow**:
    1.  Resolves the pipeline centerline path (uses coordinates from OSM/Overpass if provided, otherwise queries the `EDF/OGIM/current` GEE collection).
    2.  Creates a buffer around the centerline (default `200m`).
    3.  Loads Sentinel-1 backscatter and calculates the ratio against a 90-120 day prior baseline. Flags SAR anomalies where ratio `> 1.6`.
    4.  Loads Sentinel-2 images to detect NDVI drops `> 0.15` compared to a 90-day baseline.
    5.  Combines SAR and NDVI anomalies to map corridor disturbance.
    6.  Uses Dynamic World classifications to detect bare/built encroachment inside the buffer.
*   **Constants & Thresholds**:
    *   `DEFAULT_BUFFER_M` = `200`
    *   `RATIO_DISTURBANCE_THRESHOLD` = `1.6` (approx. +2 dB backscatter increase)
    *   `NDVI_DROP_THRESHOLD` = `0.15`
    *   `CLOUD_COVER_MAX` = `40%`.

---

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
