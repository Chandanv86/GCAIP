import sys
from unittest.mock import MagicMock

# Mock the ee module before any tests import it
class EEMock:
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        # Return a mock for any chained GEE calls
        return MagicMock()

# Inject EEMock into sys.modules
sys.modules['ee'] = EEMock()

import pytest

@pytest.fixture(autouse=True)
def mock_gee_client(monkeypatch):
    """Mock the gee_client functions so tests run offline without GEE credentials."""
    from gee import client as gee_client

    # Mock initialize
    monkeypatch.setattr(gee_client, "initialize", lambda: None)

    # Mock safe_call
    def mock_safe_call(fn, *args, **kwargs):
        # If calling size().getInfo or coordinates().getInfo, return mock values
        name = fn.__name__ if hasattr(fn, "__name__") else str(fn)
        if "getInfo" in name or "aggregate" in name:
            if "coordinates" in name:
                return [10.0, 5.0]
            if "reduceRegion" in name:
                return {"plume_signal": 0.25, "longitude": 10.0, "latitude": 5.0}
            return 5 # Mock collection size of 5 images
        if "aggregate" in name:
            return 1719888000000 # Mock timestamp (2024-07-02)
        return MagicMock()
    monkeypatch.setattr(gee_client, "safe_call", mock_safe_call)

    # Mock get_stats
    def mock_get_stats(*args, **kwargs):
        return {
            "plume_area_km2": 0.45,
            "water_area_km2": 2.5,
            "ndci_mean": 0.08,
            "ndti_mean": 0.12,
            "ndci_base": 0.04,
            "ndti_base": 0.06,
            "impact_area_km2": 0.35,
            "spm_mean": 18.5,
            "cdom_mean": 1.1,
            "lst_c": 22.4,
            "disturbed_km2": 0.12,
            "veg_loss_ha": 1.2,
            "ratio_mean": 1.4,
            "ndvi_mean": 0.45,
            "encroachment_ha": 0.8,
            "corridor_km2": 0.5,
            "area": 12.5,
            "water": 100.0,
        }
    monkeypatch.setattr(gee_client, "get_stats", mock_get_stats)

    # Mock get_tile_url
    def mock_get_tile_url(*args, **kwargs):
        from datetime import datetime, timezone, timedelta
        return "https://earthengine.googleapis.com/v1/projects/mock/maps/123/tiles/{z}/{x}/{y}", datetime.now(timezone.utc) + timedelta(hours=6)
    monkeypatch.setattr(gee_client, "get_tile_url", mock_get_tile_url)
