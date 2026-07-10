import pytest
from unittest.mock import MagicMock, patch

from gee.processors.effluent_plume import EffluentPlumeProcessor
from gee.processors.coastal_outfall import CoastalOutfallProcessor
from gee.processors.pipeline_corridor import PipelineCorridorProcessor
from services.risk_engine import RiskEngine
from services.cross_theme import CrossThemeCorrelator
from workers.tasks.theme_tasks import THEME_TASKS

# Dummy GeoJSON AOI
mock_aoi_geojson = {
    "type": "Feature",
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[10.0, 5.0], [10.1, 5.0], [10.1, 5.1], [10.0, 5.1], [10.0, 5.0]]]
    },
    "properties": {
        "name": "Mock AOI",
        "buffer_m": 250
    }
}

def test_theme_tasks_registration():
    """Verify all 10 theme tasks are correctly registered in the celery queue map."""
    assert len(THEME_TASKS) == 10
    assert "effluent_plume" in THEME_TASKS
    assert "coastal_outfall" in THEME_TASKS
    assert "pipeline_corridor" in THEME_TASKS

def test_effluent_plume_happy_path():
    """Verify effluent plume processor runs correctly and returns structured ThemeResult."""
    processor = EffluentPlumeProcessor()
    result = processor.compute(mock_aoi_geojson, ("2024-07-01", "2024-07-10"))

    assert result.error is None
    assert result.theme == "effluent_plume"
    assert result.metric_value == 0.45
    assert result.metric_unit == "km2"
    assert result.stats["cloud_threshold_used"] == 35  # default
    assert result.stats["source_collection"] == "COPERNICUS/S2_SR_HARMONIZED"

def test_effluent_plume_fallback_landsat(monkeypatch):
    """Test S2 empty, falling back to Landsat."""
    from gee import client as gee_client

    call_count = 0
    def mock_safe_call(fn, *args, **kwargs):
        nonlocal call_count
        name = fn.__name__ if hasattr(fn, "__name__") else str(fn)
        if "getInfo" in name:
            call_count += 1
            if call_count <= 4:  # S2 default, widen15, widen30, relaxed60
                return 0
            return 3  # Landsat has 3 images
        if "aggregate" in name:
            return 1719888000000
        return MagicMock()

    monkeypatch.setattr(gee_client, "safe_call", mock_safe_call)

    processor = EffluentPlumeProcessor()
    result = processor.compute(mock_aoi_geojson, ("2024-07-01", "2024-07-10"))

    assert result.error is None
    assert result.stats["source_collection"] == "LANDSAT/LC08+09"
    assert result.stats["cloud_threshold_used"] == 35

def test_effluent_plume_exhausted(monkeypatch):
    """Test all fallback tiers empty, returning error result."""
    from gee import client as gee_client

    def mock_safe_call(fn, *args, **kwargs):
        name = fn.__name__ if hasattr(fn, "__name__") else str(fn)
        if "getInfo" in name:
            return 0  # all return empty
        return MagicMock()

    monkeypatch.setattr(gee_client, "safe_call", mock_safe_call)

    processor = EffluentPlumeProcessor()
    result = processor.compute(mock_aoi_geojson, ("2024-07-01", "2024-07-10"))

    assert result.error is not None
    assert "No usable imagery found" in result.error

def test_coastal_outfall_happy_path():
    """Verify coastal outfall processor runs correctly and computes SST delta."""
    processor = CoastalOutfallProcessor()
    result = processor.compute(mock_aoi_geojson, ("2024-07-01", "2024-07-10"))

    assert result.error is None
    assert result.theme == "coastal_outfall"
    assert result.stats["delta_sst_c"] is not None
    assert result.stats["cloud_threshold_used"] == 35

def test_pipeline_corridor_happy_path_osm():
    """Verify pipeline corridor processor runs with custom GeoJSON geometry."""
    geojson_with_pipeline = dict(mock_aoi_geojson)
    geojson_with_pipeline["properties"] = {
        "pipeline_geometry": {
            "type": "LineString",
            "coordinates": [[10.0, 5.0], [10.1, 5.1]]
        }
    }

    processor = PipelineCorridorProcessor()
    result = processor.compute(geojson_with_pipeline, ("2024-07-01", "2024-07-10"))

    assert result.error is None
    assert result.theme == "pipeline_corridor"
    assert result.stats["pipeline_vector_source"] == "osm_overpass"

def test_pipeline_corridor_ogim_fallback(monkeypatch):
    """Verify pipeline corridor processor queries OGIM on missing OSM pipeline geometry."""
    processor = PipelineCorridorProcessor()
    result = processor.compute(mock_aoi_geojson, ("2024-07-01", "2024-07-10"))

    assert result.error is None
    assert result.stats["pipeline_vector_source"] == "ogim"

def test_pipeline_corridor_ogim_buffered_retry(monkeypatch):
    """Verify pipeline corridor retries with +2km buffered AOI when first bounds search returns 0."""
    from gee import client as gee_client

    call_count = 0
    def mock_safe_call(fn, *args, **kwargs):
        nonlocal call_count
        name = fn.__name__ if hasattr(fn, "__name__") else str(fn)
        if "getInfo" in name:
            if "size" in name:
                call_count += 1
                if call_count == 1:  # first OGIM size check
                    return 0
                return 4  # second (buffered) OGIM size check, or S1 size check
            return 5
        return MagicMock()

    monkeypatch.setattr(gee_client, "safe_call", mock_safe_call)

    processor = PipelineCorridorProcessor()
    result = processor.compute(mock_aoi_geojson, ("2024-07-01", "2024-07-10"))

    assert result.error is None
    assert result.stats["pipeline_vector_source"] == "ogim"

def test_risk_engine_partial_themes():
    """Verify RiskEngine computes successfully even when some themes are absent."""
    # Test with only active default themes: rainfall and landuse
    mock_results = {
        "rainfall": MagicMock(status="complete", confidence=0.8, anomaly_score=45.0, stats={"spi_7": 1.2}),
        "landuse": MagicMock(status="complete", confidence=0.9, stats={"runoff_increase_pct": 5.0, "changed_area_ha": 12.0})
    }

    engine = RiskEngine()
    score = engine.compute(mock_results)

    assert score.overall_score > 0.0
    assert score.water_stress is not None
    assert score.landuse_pressure is not None
    # Verify new fields are computed and present as None or values, not raising exceptions
    assert score.water_sanitation_pressure == 0.0
    assert score.infrastructure_integrity == 0.0

def test_cross_theme_compound_insights():
    """Verify CrossThemeCorrelator handles partial theme sets and detects new rules."""
    correlator = CrossThemeCorrelator()

    # Case 1: Rainfall + Effluent Plume
    mock_stats = {
        "rainfall": {"spi_7": 1.8},
        "effluent_plume": {"plume_extent_km2": 0.35}
    }
    insights = correlator.evaluate(mock_stats)
    assert any(i.insight_id == "runoff_driven_plume" for i in insights)

    # Case 2: Landuse + Pipeline Encroachment
    mock_stats = {
        "landuse": {
            "transitions": {"tree_to_built_ha": 2.5}
        },
        "pipeline_corridor": {"encroachment_ha": 1.5}
    }
    insights = correlator.evaluate(mock_stats)
    assert any(i.insight_id == "encroachment_confirmed" for i in insights)
