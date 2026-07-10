# GCAIP Integration Guide — Themes 8, 9, 10 (Water & Sanitation)

## 1. Register Celery tasks — `workers/tasks/theme_tasks.py`

Add imports alongside the existing processor imports:

```python
from gee.processors.effluent_plume import EffluentPlumeProcessor
from gee.processors.coastal_outfall import CoastalOutfallProcessor
from gee.processors.pipeline_corridor import PipelineCorridorProcessor
```

Add the three task functions, following the exact same `_run_theme` pattern used by
`flood_task` / `rainfall_task` / etc.:

```python
@celery_app.task(base=GEETask, bind=True, max_retries=2)
def effluent_plume_task(self, run_id, aoi_geojson, date_range, cache_key):
    return _run_theme(
        EffluentPlumeProcessor, "effluent_plume", run_id, aoi_geojson, date_range, cache_key
    )


@celery_app.task(base=GEETask, bind=True, max_retries=2)
def coastal_outfall_task(self, run_id, aoi_geojson, date_range, cache_key):
    return _run_theme(
        CoastalOutfallProcessor, "coastal_outfall", run_id, aoi_geojson, date_range, cache_key
    )


@celery_app.task(base=GEETask, bind=True, max_retries=2)
def pipeline_corridor_task(self, run_id, aoi_geojson, date_range, cache_key):
    return _run_theme(
        PipelineCorridorProcessor, "pipeline_corridor", run_id, aoi_geojson, date_range, cache_key
    )
```

Update the theme registries used by `dispatch_all_themes`:

```python
THEME_TASKS = {
    "flood": flood_task,
    "rainfall": rainfall_task,
    "reservoir": reservoir_task,
    "mangrove": mangrove_task,
    "erosion": erosion_task,
    "vegetation": vegetation_task,
    "landuse": landuse_task,
    "effluent_plume": effluent_plume_task,
    "coastal_outfall": coastal_outfall_task,
    "pipeline_corridor": pipeline_corridor_task,
}

# Themes 8-10 are opt-in per-AOI (pipeline_corridor in particular only makes sense
# when a pipeline route is present), so they are NOT added to the default
# ACTIVE_THEMES set that's dispatched for every AOI — the frontend should let the
# user explicitly enable them when relevant (industrial/coastal/pipeline AOIs).
ACTIVE_THEMES = [
    "flood", "rainfall", "reservoir", "mangrove", "erosion", "vegetation", "landuse",
]
WATER_SANITATION_THEMES = ["effluent_plume", "coastal_outfall", "pipeline_corridor"]
```

The `theme` column on `ThemeResult` (`models/theme_result.py`) is a free `VARCHAR(64)`,
so no migration is required for the new string values — but update the inline
docstring/comment listing valid themes for future readers, and add a
`CheckConstraint` migration if you want DB-level enforcement of the theme enum.

## 2. `services/risk_engine.py` — folding the new themes into the composite score

Today `Overall = (water_stress * 0.50) + (landuse_pressure * 0.50)` because only
those two sub-indices are "active." Recommended approach for the new themes:

```python
def _pollution_risk_index(self, effluent_result: dict | None, outfall_result: dict | None) -> float:
    """New sub-index: 0-100 water-quality/pollution pressure."""
    if not effluent_result and not outfall_result:
        return 0.0
    scores = []
    if effluent_result and effluent_result.get("status") == "complete":
        scores.append(effluent_result.get("anomaly_score", 0.0))
    if outfall_result and outfall_result.get("status") == "complete":
        scores.append(outfall_result.get("anomaly_score", 0.0))
    return sum(scores) / len(scores) if scores else 0.0


def _infrastructure_integrity_index(self, pipeline_result: dict | None) -> float:
    """New sub-index: 0-100 pipeline/infrastructure disturbance pressure."""
    if not pipeline_result or pipeline_result.get("status") != "complete":
        return 0.0
    return pipeline_result.get("anomaly_score", 0.0)
```

Re-weight the overall score only when the new themes were actually requested for
that AOI (do not silently zero-weight them into every run — that would dilute the
existing 7-theme score for AOIs that never asked for water-and-sanitation themes):

```python
def compute(self, results_by_theme: dict) -> RiskScore:
    has_new_themes = any(
        t in results_by_theme for t in ("effluent_plume", "coastal_outfall", "pipeline_corridor")
    )
    water_stress = self._water_stress_index(results_by_theme)
    landuse_pressure = self._landuse_pressure_index(results_by_theme)

    if not has_new_themes:
        overall = (water_stress * 0.50) + (landuse_pressure * 0.50)
    else:
        pollution_risk = self._pollution_risk_index(
            results_by_theme.get("effluent_plume"), results_by_theme.get("coastal_outfall")
        )
        infra_risk = self._infrastructure_integrity_index(results_by_theme.get("pipeline_corridor"))
        overall = (
            water_stress * 0.30
            + landuse_pressure * 0.25
            + pollution_risk * 0.30
            + infra_risk * 0.15
        )

    return RiskScore(overall=overall, band=self._band_for(overall), ...)
```

(Exact weights are a policy decision for the GCAIP team — the numbers above are a
reasonable starting split, not a scientifically derived optimum.)

## 3. `services/cross_theme.py` — new compound-risk rules

Add to `CrossThemeCorrelator.evaluate()`:

```python
# Rule 7: Effluent Plume + Reservoir — pollution concentrating in a filling reservoir
if (
    stats_by_theme.get("effluent_plume", {}).get("plume_extent_km2", 0) > 0.05
    and stats_by_theme.get("reservoir", {}).get("fill_fraction_pct", 0) > 85
):
    insights.append(CrossInsight(
        rule="pollution_accumulation_risk",
        severity="WARNING",
        message="Effluent plume detected upstream of a near-full reservoir — "
                "pollutant concentration risk as fill approaches capacity.",
    ))

# Rule 8: Coastal Outfall + Coastal Erosion — infrastructure exposure at eroding shoreline
if (
    stats_by_theme.get("coastal_outfall", {}).get("outfall_impact_area_km2", 0) > 0.1
    and stats_by_theme.get("erosion", {}).get("mean_epr_m_yr", 0) < -1.0
):
    insights.append(CrossInsight(
        rule="outfall_shoreline_exposure",
        severity="WATCH",
        message="Coastal outfall plume detected in an actively eroding shoreline "
                "segment — outfall infrastructure may become exposed or undermined.",
    ))

# Rule 9: Pipeline Corridor + Flood — flood-driven pipeline exposure/washout risk
if (
    stats_by_theme.get("pipeline_corridor", {}).get("disturbed_corridor_length_m", 0) > 100
    and stats_by_theme.get("flood", {}).get("flooded_km2", 0) > 0
):
    insights.append(CrossInsight(
        rule="pipeline_flood_exposure",
        severity="WARNING",
        message="Active flooding coincides with a disturbed pipeline corridor segment "
                "— elevated risk of scouring, washout, or leak propagation.",
    ))

# Rule 10: Effluent Plume + Mangrove — pollution stress on mangrove buffer zones
if (
    stats_by_theme.get("effluent_plume", {}).get("plume_extent_km2", 0) > 0.05
    and stats_by_theme.get("mangrove", {}).get("net_change_ha", 0) < -5
):
    insights.append(CrossInsight(
        rule="mangrove_pollution_stress",
        severity="WATCH",
        message="Effluent plume detected adjacent to a mangrove zone showing net loss "
                "— pollution may be compounding degradation of the storm-surge buffer.",
    ))
```

## 4. AOI payload changes needed for Pipeline Corridor (frontend / API layer)

`PipelineCorridorProcessor` expects, optionally, on the AOI GeoJSON:

```json
{
  "type": "Feature",
  "geometry": { "...": "..." },
  "properties": {
    "buffer_m": 200,
    "pipeline_geometry": {
      "type": "LineString",
      "coordinates": [[lon1, lat1], [lon2, lat2], "..."]
    }
  }
}
```

- If `pipeline_geometry` is present (populated by calling `OverpassClient.get_infrastructure`
  with an added `man_made=pipeline` query — a one-line extension to the existing Overpass QL
  builder in `integrations/overpass.py`), the processor uses that authentic OSM vector directly.
- If absent, the processor queries `EDF/OGIM/current` natively inside GEE and filters to
  pipeline features intersecting the AOI — no separate backend integration is required for
  this path since it runs entirely inside Earth Engine.
- If neither source yields a pipeline feature, the processor returns a graceful
  `ThemeResult.error_result`, and the frontend should prompt the user to draw/attach a
  pipeline route for that AOI.

## 5. Frontend theme registration

Add the three themes to the React theme-config list (alongside their tile-layer palette,
units, and card labels) so `useSSEStream`'s `theme_complete` handler renders their cards:

```ts
export const WATER_SANITATION_THEMES: ThemeConfig[] = [
  { id: "effluent_plume", label: "Effluent Plume", unit: "km²", icon: "droplet" },
  { id: "coastal_outfall", label: "Coastal Outfall", unit: "km²", icon: "waves" },
  { id: "pipeline_corridor", label: "Pipeline Corridor", unit: "m", icon: "route" },
];
```

Since Themes 8–10 are opt-in (see §1), gate their layer toggle behind an AOI-type or
user selection (e.g., "Industrial / Coastal / Pipeline monitoring" AOI category) rather
than always dispatching them alongside the core seven.
