"""
WorldPop REST API client — population count within bounding box.
Fallback: GEE WorldPop/GP/100m/pop/2020 raster zonal sum.
Cache: 24h TTL in Redis per bbox hash.
"""
import hashlib
import json
import structlog

import httpx

from config import settings

log = structlog.get_logger(__name__)


class WorldPopClient:
    """Fetches population counts from WorldPop REST or GEE fallback."""

    BASE_URL = settings.WORLDPOP_BASE_URL

    def get_population(self, bbox: list[float]) -> int | None:
        """
        Args:
            bbox: [min_lon, min_lat, max_lon, max_lat]

        Returns:
            Integer population count, or None if unavailable
        """
        cache_key = self._cache_key(bbox)
        cached = self._redis_get(cache_key)
        if cached is not None:
            return cached

        # Try REST API first
        try:
            pop = self._fetch_rest(bbox)
            if pop is not None:
                self._redis_set(cache_key, pop)
                return pop
        except Exception as exc:
            log.warning("worldpop.rest_failed", error=str(exc))

        # GEE fallback
        try:
            pop = self._fetch_gee(bbox)
            if pop is not None:
                self._redis_set(cache_key, pop)
            return pop
        except Exception as exc:
            log.warning("worldpop.gee_failed", error=str(exc))
            return None

    def _fetch_rest(self, bbox: list[float]) -> int | None:
        min_lon, min_lat, max_lon, max_lat = bbox
        # WorldPop API: /pop/wpgpas?iso3=GLOBAL&year=2020&format=json
        # Using bounding box query
        url = f"{self.BASE_URL}/pop/wpgpas"
        params = {
            "iso3": "GLOBAL",
            "year": 2020,
            "bbox": f"{min_lon},{min_lat},{max_lon},{max_lat}",
            "format": "json",
        }
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            # Extract population sum from response
            total = sum(
                item.get("population", 0) or 0
                for item in data.get("data", [])
            )
            return int(total) if total > 0 else None

    @staticmethod
    def _fetch_gee(bbox: list[float]) -> int | None:
        """Use GEE WorldPop raster as fallback — zonal sum within bbox."""
        import ee
        from gee import client as gee_client
        gee_client.initialize()

        min_lon, min_lat, max_lon, max_lat = bbox
        aoi = ee.Geometry.BBox(min_lon, min_lat, max_lon, max_lat)

        pop_image = ee.ImageCollection("WorldPop/GP/100m/pop").filter(
            ee.Filter.eq("year", 2020)
        ).mosaic()

        stats = gee_client.get_stats(
            image=pop_image,
            aoi=aoi,
            scale=100,
            reducer=ee.Reducer.sum(),
        )
        total = sum(v for v in stats.values() if isinstance(v, (int, float)))
        return int(total) if total > 0 else None

    @staticmethod
    def _cache_key(bbox: list[float]) -> str:
        return "gcaip:worldpop:" + hashlib.md5(
            json.dumps(bbox, sort_keys=True).encode()
        ).hexdigest()[:12]

    @staticmethod
    def _redis_get(key: str) -> int | None:
        try:
            import redis as redis_lib
            r = redis_lib.from_url(settings.REDIS_URL)
            val = r.get(key)
            return int(val) if val else None
        except Exception:
            return None

    @staticmethod
    def _redis_set(key: str, value: int) -> None:
        try:
            import redis as redis_lib
            r = redis_lib.from_url(settings.REDIS_URL)
            r.setex(key, settings.REDIS_TTL_OSM, str(value))
        except Exception:
            pass
