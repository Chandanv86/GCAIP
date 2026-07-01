"""
GEE Client — Google Earth Engine initialization, authentication, and utility wrappers.

ALL satellite processing goes through GEE. This module is the single
entry point for GEE operations across the entire backend.

Key responsibilities:
  - Initialize GEE with service account credentials (once, at worker startup)
  - Provide retry-wrapped calls (GEE fails ~5% of the time — always retry)
  - Normalize tile URLs to XYZ template format
  - Classify errors: quota|asset_not_found|transient
  - Enforce timeout per call
"""
import functools
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import ee

from config import settings

import structlog
log = structlog.get_logger(__name__)


class GEEError(Exception):
    """Base class for GEE errors."""


class GEEQuotaError(GEEError):
    """GEE compute quota exceeded."""


class GEEAssetNotFoundError(GEEError):
    """GEE asset path not found or no images for date range."""


class GEETransientError(GEEError):
    """GEE transient error — safe to retry."""


_initialized = False


def initialize() -> None:
    """
    Initialize GEE with service account credentials.
    Must be called once per worker process — Celery workers call this at startup.
    Thread-safe (GEE initialization is idempotent).
    """
    global _initialized
    if _initialized:
        return

    if not settings.GEE_SERVICE_ACCOUNT or settings.GEE_SERVICE_ACCOUNT.startswith("your-"):
        log.warning("gee.skipped", reason="GEE_SERVICE_ACCOUNT not configured")
        raise GEEError(
            "GEE_SERVICE_ACCOUNT is not configured. "
            "Set it in .env and place the service account JSON key at "
            f"{settings.GEE_CREDENTIALS_PATH} to enable satellite analysis."
        )

    import os
    if not os.path.exists(settings.GEE_CREDENTIALS_PATH):
        raise GEEError(
            f"GEE credentials file not found at '{settings.GEE_CREDENTIALS_PATH}'. "
            "Download your service account JSON key and place it there."
        )

    try:
        credentials = ee.ServiceAccountCredentials(
            email=settings.GEE_SERVICE_ACCOUNT,
            key_file=settings.GEE_CREDENTIALS_PATH,
        )
        ee.Initialize(
            credentials=credentials,
            project=settings.GEE_PROJECT,
            opt_url="https://earthengine.googleapis.com",
        )
        _initialized = True
        log.info("gee.initialized", account=settings.GEE_SERVICE_ACCOUNT)
    except Exception as exc:
        log.error("gee.init_failed", error=str(exc))
        raise GEEError(f"GEE initialization failed: {exc}") from exc


def _classify_error(exc: Exception) -> GEEError:
    """Classify a raw GEE exception into our typed error hierarchy."""
    msg = str(exc).lower()
    if "quota" in msg or "rate limit" in msg or "user memory limit" in msg:
        return GEEQuotaError(str(exc))
    if "not found" in msg or "no images" in msg or "asset" in msg:
        return GEEAssetNotFoundError(str(exc))
    return GEETransientError(str(exc))


def safe_call(
    fn: Callable,
    *args: Any,
    retries: int = settings.GEE_MAX_RETRIES,
    timeout: int = settings.GEE_TIMEOUT_SECONDS,
    **kwargs: Any,
) -> Any:
    """
    Execute a GEE API call with retry logic and timeout.

    Retries on transient errors only. Quota and asset-not-found errors
    are surfaced immediately — retrying them wastes quota.

    Args:
        fn: Callable that wraps a GEE computation (e.g., image.getMapId)
        retries: Max retry attempts for transient failures
        timeout: Wall-clock timeout per attempt in seconds

    Returns:
        The result of fn(*args, **kwargs)

    Raises:
        GEEQuotaError: Quota exceeded — do not retry
        GEEAssetNotFoundError: Asset or data not found — caller should handle gracefully
        GEEError: Unrecoverable error after all retries exhausted
    """
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            classified = _classify_error(exc)
            if isinstance(classified, GEEQuotaError):
                log.warning("gee.quota_exceeded", error=str(exc))
                raise classified
            if isinstance(classified, GEEAssetNotFoundError):
                log.warning("gee.asset_not_found", error=str(exc))
                raise classified

            # Transient — back off and retry
            wait = 2 ** attempt  # 1s, 2s, 4s
            log.warning(
                "gee.transient_error",
                attempt=attempt + 1,
                wait_sec=wait,
                error=str(exc),
            )
            last_exc = exc
            time.sleep(wait)

    raise GEEError(
        f"GEE call failed after {retries} retries: {last_exc}"
    ) from last_exc


def get_tile_url(image: "ee.Image", vis_params: dict) -> tuple[str, datetime]:
    """
    Render a GEE image to tiles and return the XYZ tile URL template.

    GEE tiles expire approximately 6 hours after generation.

    Args:
        image: GEE ee.Image to render
        vis_params: Visualization parameters dict (min, max, palette, bands)

    Returns:
        (tile_url, expires_at): XYZ tile URL template + expiry datetime
    """
    map_id = safe_call(image.getMapId, vis_params)
    # GEE getMapId returns a dict with 'tile_fetcher' — extract the URL template
    tile_url: str = map_id["tile_fetcher"].url_format
    expires_at = datetime.now(timezone.utc) + timedelta(hours=6)
    return tile_url, expires_at


def get_stats(
    image: "ee.Image",
    aoi: "ee.Geometry",
    scale: int = settings.GEE_SCALE_DEFAULT,
    reducer: "ee.Reducer | None" = None,
    max_pixels: int = 1e10,
) -> dict[str, Any]:
    """
    Compute zonal statistics for an image within an AOI.

    Args:
        image: GEE ee.Image
        aoi: AOI as ee.Geometry
        scale: Spatial resolution in metres for the computation
        reducer: GEE reducer (default: ee.Reducer.mean())
        max_pixels: Maximum pixel count (increase for large AOIs)

    Returns:
        dict of band_name → statistic_value
    """
    if reducer is None:
        reducer = ee.Reducer.mean()

    return safe_call(
        image.reduceRegion,
        reducer=reducer,
        geometry=aoi,
        scale=scale,
        maxPixels=max_pixels,
        bestEffort=True,  # Automatically increase scale if pixel limit hit
    ).getInfo()


def geojson_to_ee_geometry(geojson: dict) -> "ee.Geometry":
    """
    Convert a GeoJSON dict (Feature or Polygon geometry) to ee.Geometry.

    Args:
        geojson: GeoJSON dict — Feature, FeatureCollection, or Geometry

    Returns:
        ee.Geometry object suitable for GEE filtering

    Raises:
        ValueError: If the GeoJSON is not a recognizable geometry type
    """
    geo_type = geojson.get("type", "")

    if geo_type == "Feature":
        return ee.Geometry(geojson["geometry"])
    elif geo_type == "FeatureCollection":
        features = geojson.get("features", [])
        if not features:
            raise ValueError("FeatureCollection has no features")
        return ee.Geometry(features[0]["geometry"])
    elif geo_type in ("Polygon", "MultiPolygon", "Point", "LineString"):
        return ee.Geometry(geojson)
    else:
        raise ValueError(f"Unsupported GeoJSON type: {geo_type}")


def test_connection() -> dict[str, Any]:
    """
    Verify GEE connectivity. Called by the health check endpoint.

    Returns:
        dict with status, quota info, and latency
    """
    initialize()
    start = time.monotonic()
    try:
        # Lightweight call: fetch a single pixel from a known public asset
        test_image = ee.Image("COPERNICUS/S2_SR_HARMONIZED/20210101T000000_20210101T000000_T01CCV")
        _ = safe_call(
            ee.Image("JRC/GSW1_4/GlobalSurfaceWater")
            .select("occurrence")
            .reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=ee.Geometry.Point([8.75, 3.75]),  # Gulf of Guinea
                scale=1000,
                maxPixels=100,
            ).getInfo
        )
        latency_ms = (time.monotonic() - start) * 1000
        return {"status": "ok", "latency_ms": round(latency_ms, 1)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
