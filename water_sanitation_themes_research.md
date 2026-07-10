# GCAIP — Water & Sanitation Expansion: Research Report
### Themes 8–10: Effluent Discharge Plume · Coastal Outfall Plume · Pipeline Corridor

This report is written to sit alongside `gcaip_project_report.txt` and follows the same
conventions used by Themes 1–7 (`BaseThemeProcessor`, `ThemeResult`, `gee_client.safe_call`,
zonal-stats-only egress, 6-hour tile caching).

---

## THEME 8 — EFFLUENT DISCHARGE PLUME

**Objective:** detect and size water-quality anomaly plumes (eutrophication + turbidity) from
point-source and diffuse discharges into inland water bodies (rivers, lakes, reservoirs).

### Datasets

| Role | Collection ID | Res. | Revisit | Notes |
|---|---|---|---|---|
| Primary | `COPERNICUS/S2_SR_HARMONIZED` | 10 m (20 m for B11) | 5 days (2–3 with overlap) | Surface reflectance, has SCL band |
| Fallback 1 (cloud/latency) | `LANDSAT/LC08/C02/T1_L2`, `LANDSAT/LC09/C02/T1_L2` | 30 m | 16 days (8 combined) | Longer historical baseline, coarser |
| Fallback 2 (wide water bodies, persistent cloud) | `COPERNICUS/S3/OLCI` (via `COPERNICUS/S3/OLCI` L1B or EUMETSAT-derived L2 water products) | 300 m | Daily | Only usable once AOI water area ≫ pixel size |
| Baseline / seasonal reference | Same S2 collection, prior-year ±30-day window | 10 m | — | Same-sensor baseline avoids cross-sensor bias |

### Preprocessing
1. **Cloud/shadow masking** — reuse `BaseThemeProcessor.apply_s2_cloud_mask()` (SCL keep-classes 4/5/6); additionally drop SCL 3 (cloud shadow), 8/9 (cloud medium/high prob), 10 (cirrus), 11 (snow) explicitly for the water-quality case since the base mask alone is tuned for land.
2. **Water isolation (MNDWI)** — `MNDWI = (Green − SWIR1) / (Green + SWIR1) = (B3 − B11) / (B3 + B11)`, threshold `MNDWI > 0.1` → water mask. MNDWI is preferred over NDWI(B3,B8) here because SWIR1 is far less sensitive to suspended-sediment brightening in the discharge zone itself, which would otherwise erode the water mask exactly where we need it most.
3. **Atmospheric correction** — `S2_SR_HARMONIZED` is already Sen2Cor-corrected (surface reflectance); we do **not** attempt a secondary C2RCC/ACOLITE pass server-side (not exposed as a GEE-native op). This is logged as a known accuracy caveat in `confidence` scoring rather than silently ignored.
4. **Glint avoidance** — flat inland waters rarely need explicit sun-glint correction at S2 geometry; skip for rivers/lakes (contrast Theme 9, which does need it for marine surfaces).

### Indices
- **NDCI** (chlorophyll-a proxy, Mishra & Mishra 2012 formulation adapted to S2 red-edge):
  `NDCI = (B5 − B4) / (B5 + B4)`
- **NDTI** (turbidity, Lacaux et al. 2007):
  `NDTI = (B4 − B3) / (B4 + B3)`
- **Plume mask:** `Plume = (NDCI > 0.05) AND (NDTI > 0.10) AND water_mask`
- **Baseline delta:** current-period zonal mean NDCI/NDTI vs. the prior-year seasonal composite mean/std, expressed as a z-score using the same `compute_anomaly_score()` helper already defined on `BaseThemeProcessor` — this keeps the anomaly math identical in spirit to Themes 6/7.

### Reducers / Vis
- `ee.Reducer.sum()` on `ee.Image.pixelArea()` masked by `Plume`, scale 10 m → `plume_extent_km2`.
- `ee.Reducer.mean()` for `ndci_mean`, `ndti_mean`, both plain and baseline.
- `ee.Reducer.sum()` for `water_area_km2` (denominator for normalized anomaly score).
- Palette: `["#1a9850", "#91cf60", "#d9ef8b", "#fee08b", "#fc8d59", "#67001f"]` (green→dark brown/red, low→high turbidity/chlorophyll).

### Metrics
`plume_extent_km2`, confidence from cloud-free S2 scene count in-window (`0.5 + 0.1·scene_count`, capped 1.0), `data_age_hours` from latest scene `system:time_start`, `anomaly_score = min(100, (plume_extent_km2 / max(water_area_km2, 0.01)) * 300)`.

---

## THEME 9 — COASTAL OUTFALL PLUME

**Objective:** map the extent, dispersion bearing, and (where thermal) temperature signature of
marine outfalls — municipal wastewater, agricultural runoff, or power-plant cooling water.

### Datasets

| Role | Collection ID | Res. | Revisit | Notes |
|---|---|---|---|---|
| Primary optical | `COPERNICUS/S2_SR_HARMONIZED` | 10 m | 5 days | SPM/CDOM proxies |
| Thermal | `LANDSAT/LC08/C02/T1_L2`, `LANDSAT/LC09/C02/T1_L2` (ST_B10, already scaled to Kelvin via `0.00341802·DN + 149.0`) | 100 m native / 30 m product grid | 16 days (8 combined) | Only sensor with usable thermal for point-source plumes |
| Wide-area / persistent cloud | `COPERNICUS/S3/OLCI` | 300 m | Daily | Large bays / river mouths only |
| SST context (ambient offshore reference) | `NASA/OCEANCOLOR/MODIS-Aqua/L3SMI` (band `sst`) | 4 km | Daily | Used only to build the *ambient* baseline, not the plume detail |
| Wind/tide context | `ECMWF/ERA5_LAND/HOURLY` | ~11 km | Hourly | Same asset already used by Theme 5 (erosion) for wave-force proxy |

### Preprocessing
1. **Marine boundary isolation** — intersect `ESA/WorldCover/v200` water class (80) with a dynamic S2 NDWI (`(B3−B8)/(B3+B8) > 0`) mask; erase anything inside a small land buffer to avoid intertidal noise.
2. **Sun-glint suppression** — since marine surfaces at low sun-elevation produce specular glint that swamps SPM/CDOM signal, mask pixels where SWIR1 (B11) reflectance exceeds a glint threshold (`B11 > 0.02` after SR scaling is a reasonable first-pass flag, since open ocean water is essentially opaque in SWIR — any signal there is glint or cloud, not water-leaving radiance).
3. **Tidal context** — GCAIP does not currently host a tide-gauge integration; this processor stubs a `tidal_stage` field as `"unknown"` and folds a fixed confidence penalty (−0.1) into `confidence` until a tide API (e.g., NOAA CO-OPS for US coasts, or a global model such as FES2014) is wired into `integrations/`.

### Indices / algorithms
- **SPM (Suspended Particulate Matter) proxy**, single-band red algorithm (Nechad et al. 2010 form):
  `SPM = (A · ρ_red) / (1 − ρ_red / C) `, with default calibration constants `A = 355.85`, `C = 0.1728` (generic global values — a site-specific in-situ calibration is strongly recommended before treating outputs as absolute mg/L).
- **CDOM proxy** (blue/green ratio, qualitative, not absolutely calibrated): `CDOM_index = B2 / B3`. Rising values track increasing dissolved organic/humic loading.
- **Thermal plume (ΔSST):** `ΔSST = LST_pixel − LST_ambient`, where `LST_ambient` is the zonal mean of Landsat ST_B10 over an offshore annulus 1–3 km outside the AOI (or MODIS SST if Landsat coverage is thin). `HIGH` thermal-plume flag when `ΔSST > 1.5 °C` over an area exceeding 0.05 km².
- **Plume front/edge detection:** Sobel gradient magnitude on the combined SPM/CDOM raster using `ee.Kernel.sobel()` convolved via `image.convolve()`; threshold the gradient magnitude at its 90th-percentile zonal value to trace the plume boundary.
- **Dispersion bearing:** compute the zonal centroid of the plume mask (`ee.Image.pixelLonLat()` reduced with `ee.Reducer.mean()` inside the plume) and the AOI/outfall-anchor centroid (assumed to be the AOI centroid unless the AOI GeoJSON carries an explicit `outfall_point` property — see code). Bearing is then a simple planar `atan2` computed client-side on the two returned lon/lat scalars (safe: this is a two-float computation on already-aggregated stats, not raw imagery).

### Reducers / Vis
- `ee.Reducer.sum()` on pixel area for `outfall_impact_area_km2`.
- `ee.Reducer.mean()` for zonal SPM, CDOM, ΔSST.
- Palette: `["#08306b", "#2171b5", "#6baed6", "#fee391", "#fe9929", "#d94801"]` (cool blue ambient → warm yellow/orange plume core).

### Metrics
`outfall_impact_area_km2`, `dispersion_bearing_deg`, confidence combines tidal-completeness penalty + cloud-free fraction, `data_age_hours` from the freshest contributing sensor.

---

## THEME 10 — PIPELINE CORRIDOR

**Objective:** monitor a buffered linear corridor along pipeline routes for vegetation
disturbance, soil exposure, and encroachment that could indicate leaks, erosion, illegal
tapping, or unauthorized construction.

### Datasets

| Role | Collection ID | Res. | Revisit | Notes |
|---|---|---|---|---|
| SAR (soil/roughness) | `COPERNICUS/S1_GRD` (VV + VH, IW mode) | 10 m | 6–12 days | Backscatter ratio + (where SLC available, outside GEE GRD) coherence proxy |
| Optical (vegetation) | `COPERNICUS/S2_SR_HARMONIZED` | 10 m | 5 days | NDVI corridor time series |
| LULC baseline | `GOOGLE/DYNAMICWORLD/V1` | 10 m | Near-daily (per S2 revisit) | Bare/built encroachment classes 6 & 7 |
| **Real pipeline vector — GEE-native** | `EDF/OGIM/current` (Environmental Defense Fund Oil & Gas Infrastructure Mapping database) | vector | static, versioned | `ee.FeatureCollection`; filter `CATEGORY` for entries containing `"PIPELINE"` (the live catalog's exact category string should be confirmed against the current OGIM attribute schema at run time, since EDF revises category labels between versions — the processor below filters defensively with a case-insensitive substring match rather than a hardcoded exact string) |
| **Real pipeline vector — OSM fallback** | OpenStreetMap via the existing `OverpassClient` (`integrations/overpass.py`), tag `["man_made"="pipeline"]` | vector | live query | Returned as GeoJSON LineString/MultiLineString and injected into the AOI payload |

### Preprocessing
1. **Corridor geometry resolution** (priority order):
   1. If the AOI GeoJSON already carries a `pipeline_geometry` property (populated upstream by the FastAPI layer from an Overpass fetch) — use it directly as ground truth.
   2. Else, query `EDF/OGIM/current`, `.filterBounds(aoi_geometry)`, filter `CATEGORY` matching `/PIPELINE/i`, and use the returned `ee.FeatureCollection` geometry.
   3. Else (no vector found in either source) — fail gracefully via `ThemeResult.error_result`, since a corridor processor without a corridor geometry cannot produce a meaningful buffer.
2. **Buffering** — `geometry.buffer(buffer_m)` where `buffer_m` defaults to 200 m (configurable 100–500 m per the AOI's `properties.buffer_m`), then `.union()` across all matched line segments to avoid double counting overlapping buffers.
3. **SAR speckle reduction** — GRD (not SLC) is the only S1 product exposed in the public GEE catalog, so true InSAR coherence change detection (which requires SLC phase data) is **not achievable server-side in GEE** with public assets; the processor instead computes a **backscatter-ratio proxy** and applies a `focal_median()` spatial speckle filter (approximating a Refined Lee filter, which GEE does not ship as a built-in) before ratioing. This limitation is stated explicitly rather than silently claiming full CCD.
4. **Co-registration** — handled automatically by GEE's internal reprojection when reducing collections to a common grid at request time; no extra step needed for GRD-to-GRD ratios.

### Algorithms
- **Backscatter ratio:** `ratio = VV_current / VV_baseline` (baseline = prior 90–120 day median composite). `ratio > 1.6` (≈ +2 dB) flags likely excavation/vegetation removal/soil exposure.
- **NDVI drop:** `ΔNDVI = NDVI_baseline(90–30 days prior) − NDVI_current(0–30 days)`. `ΔNDVI > 0.15` flags canopy clearing.
- **Disturbance mask:** `Disturbance = (ratio > 1.6) OR (ΔNDVI > 0.15)`, clipped to the corridor buffer only.
- **Bare/built encroachment:** Dynamic World mode-composite label ∈ {6 (built), 7 (bare)} inside the buffer, compared against the same baseline classes 12 months prior.
- **Disturbed length proxy:** since a raster disturbance mask does not directly yield a 1-D "length," the processor approximates `disturbed_corridor_length_m ≈ (disturbed_area_km² × 1,000,000) / (2 × buffer_m)` — i.e., disturbed area divided by the known corridor width. This is stated as an approximation; a rigorous version would rasterize/vectorize the disturbance mask and measure overlap length against the actual centerline, which is a candidate Phase-2 enhancement using `ee.Image.reduceToVectors()`.
- **Vegetation loss:** `ee.Reducer.sum()` of pixel area (ha) where `ΔNDVI > 0.15`.

### Reducers / Vis
- `ee.Reducer.sum()` for disturbed area (km²) and vegetation loss (ha), scale 10 m.
- `ee.Reducer.mean()` for corridor-average ratio and NDVI.
- Palette: black corridor line with red disturbance hotspot fill — `{"disturbance": ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"], "corridor_line": "#000000"}`.

### Metrics
`disturbed_corridor_length_m`, `vegetation_loss_ha`, confidence combines S1+S2 scene-count coverage and whether the vector came from OGIM (static, high certainty of route) vs. OSM (variable completeness, small confidence penalty if geometry is sparse/short).

---

## Cross-Cutting Engineering Notes

- All three processors strictly follow the "no raw imagery" rule: only `reduceRegion` stats (JSON) and `getMapId()` XYZ tile templates ever leave GEE.
- All three wrap GEE calls through `gee_client.safe_call`, and catch `GEEAssetNotFoundError` to return `ThemeResult.error_result(theme, message)` rather than raising.
- Known accuracy caveats (no true C2RCC atmospheric correction, no tide integration yet, GRD-only so no true InSAR coherence, disturbance-length is an area/width proxy) are surfaced in each `ThemeResult.stats["caveats"]` payload so the frontend/analyst is never misled into treating these as lab-grade retrievals.
