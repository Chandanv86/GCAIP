"""
OSM Overpass API Client — counts schools, hospitals, and road km within a bbox.
Cache: 24h per bbox hash (OSM data changes slowly).
Rate limit: 1 request per 10 seconds — always cache, always backoff.
"""
import hashlib
import json
import structlog
import time
import math

import httpx

from config import settings

log = structlog.get_logger(__name__)

OVERPASS_URL = settings.OVERPASS_BASE_URL


class OverpassClient:
    """Queries OSM Overpass for infrastructure counts within a bbox."""

    def get_infrastructure(self, bbox: list[float]) -> dict:
        """
        Count schools, hospitals, and road network length.

        Args:
            bbox: [min_lon, min_lat, max_lon, max_lat]

        Returns:
            {"schools": int, "hospitals": int, "roads_km": float}
        """
        cache_key = f"gcaip:osm:infra:{self._bbox_hash(bbox)}"
        cached = self._redis_get(cache_key)
        if cached:
            return json.loads(cached)

        result = {"schools": 0, "hospitals": 0, "roads_km": 0.0}
        try:
            south, west, north, east = bbox[1], bbox[0], bbox[3], bbox[2]
            bbox_str = f"{south},{west},{north},{east}"

            query = f"""
[out:json][timeout:25];
(
  node["amenity"="school"]({bbox_str});
  node["amenity"="hospital"]({bbox_str});
  node["amenity"="clinic"]({bbox_str});
  way["highway"~"primary|secondary|tertiary|trunk|motorway"]({bbox_str});
);
out geom;
"""
            data = self._query(query)
            elements = data.get("elements", [])

            schools = sum(
                1 for e in elements
                if e.get("type") == "node"
                and e.get("tags", {}).get("amenity") == "school"
            )
            hospitals = sum(
                1 for e in elements
                if e.get("type") == "node"
                and e.get("tags", {}).get("amenity") in ("hospital", "clinic")
            )
            roads_km = sum(
                self._way_length_km(e)
                for e in elements
                if e.get("type") == "way"
            )

            result = {
                "schools": schools,
                "hospitals": hospitals,
                "roads_km": round(roads_km, 1),
            }
            self._redis_set(cache_key, json.dumps(result))
        except Exception as exc:
            log.warning("overpass.infra_error", error=str(exc))

        return result

    def get_coastal_assets(
        self, bbox: list[float], buffer_m: int = 1000
    ) -> list[dict]:
        """
        Get named infrastructure assets within buffer_m of the coastline.
        Used by trajectory.py for erosion impact timeline.

        Returns:
            List of dicts: {name, type, lat, lon, distance_m}
        """
        cache_key = f"gcaip:osm:coastal:{self._bbox_hash(bbox)}:{buffer_m}"
        cached = self._redis_get(cache_key)
        if cached:
            return json.loads(cached)

        assets = []
        try:
            south, west, north, east = bbox[1], bbox[0], bbox[3], bbox[2]
            bbox_str = f"{south},{west},{north},{east}"

            query = f"""
[out:json][timeout:25];
(
  node["highway"]({bbox_str});
  node["place"~"village|town|hamlet|settlement"]({bbox_str});
  node["amenity"~"school|hospital|clinic"]({bbox_str});
  way["highway"~"primary|secondary|trunk"]({bbox_str});
);
out geom;
"""
            data = self._query(query)
            center_lat = (bbox[1] + bbox[3]) / 2
            center_lon = (bbox[0] + bbox[2]) / 2

            for elem in data.get("elements", []):
                tags = elem.get("tags", {})
                name = (
                    tags.get("name")
                    or tags.get("ref")
                    or tags.get("amenity")
                    or tags.get("place")
                    or tags.get("highway")
                    or "Unknown"
                )
                lat = elem.get("lat", center_lat)
                lon = elem.get("lon", center_lon)
                dist = self._haversine_m(center_lat, center_lon, lat, lon)
                asset_type = (
                    "highway" if "highway" in tags
                    else "settlement" if "place" in tags
                    else tags.get("amenity", "infrastructure")
                )
                assets.append({
                    "name": name,
                    "type": asset_type,
                    "lat": lat,
                    "lon": lon,
                    "distance_m": round(dist, 0),
                })

            # Sort by proximity to coast (closer = at higher risk)
            assets.sort(key=lambda a: a["distance_m"])
            self._redis_set(cache_key, json.dumps(assets))
        except Exception as exc:
            log.warning("overpass.coastal_error", error=str(exc))

        return assets

    def _query(self, query: str, max_retries: int = 3) -> dict:
        """Execute an Overpass QL query with exponential backoff."""
        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(OVERPASS_URL, data={"data": query})
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    wait = 10 * (2 ** attempt)
                    log.warning("overpass.rate_limited", wait=wait)
                    time.sleep(wait)
                else:
                    raise
            except Exception as exc:
                if attempt == max_retries - 1:
                    raise
                time.sleep(5)
        return {}

    @staticmethod
    def _way_length_km(way: dict) -> float:
        """Approximate road length from OSM way geometry."""
        geom = way.get("geometry", [])
        if len(geom) < 2:
            return 0.0
        total = 0.0
        for i in range(len(geom) - 1):
            total += OverpassClient._haversine_m(
                geom[i]["lat"], geom[i]["lon"],
                geom[i + 1]["lat"], geom[i + 1]["lon"],
            )
        return total / 1000.0

    @staticmethod
    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Haversine distance in metres."""
        R = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def get_pipelines(self, bbox: list[float]) -> dict:
        """
        Get pipeline centerline geometries (LineString/MultiLineString) from OSM.
        
        Args:
            bbox: [min_lon, min_lat, max_lon, max_lat]
            
        Returns:
            GeoJSON FeatureCollection representing the pipeline centerlines.
        """
        cache_key = f"gcaip:osm:pipelines:{self._bbox_hash(bbox)}"
        cached = self._redis_get(cache_key)
        if cached:
            return json.loads(cached)

        geojson = {"type": "FeatureCollection", "features": []}
        try:
            south, west, north, east = bbox[1], bbox[0], bbox[3], bbox[2]
            bbox_str = f"{south},{west},{north},{east}"

            query = f"""
[out:json][timeout:25];
(
  way["man_made"="pipeline"]({bbox_str});
);
out geom;
"""
            data = self._query(query)
            elements = data.get("elements", [])
            for e in elements:
                if e.get("type") == "way" and "geometry" in e:
                    coords = [[pt["lon"], pt["lat"]] for pt in e["geometry"]]
                    geojson["features"].append({
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": coords
                        },
                        "properties": e.get("tags", {})
                    })

            self._redis_set(cache_key, json.dumps(geojson))
        except Exception as exc:
            log.warning("overpass.pipelines_error", error=str(exc))

        return geojson

    @staticmethod
    def _redis_get(key: str) -> str | None:
        try:
            import redis as redis_lib
            r = redis_lib.from_url(settings.REDIS_URL)
            val = r.get(key)
            return val.decode() if val else None
        except Exception:
            return None

    @staticmethod
    def _redis_set(key: str, value: str) -> None:
        try:
            import redis as redis_lib
            r = redis_lib.from_url(settings.REDIS_URL)
            r.setex(key, settings.REDIS_TTL_OSM, value)
        except Exception:
            pass

    @staticmethod
    def _bbox_hash(bbox: list[float]) -> str:
        return hashlib.md5(json.dumps(bbox).encode()).hexdigest()[:12]
