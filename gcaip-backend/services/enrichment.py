"""
Enrichment Service — converts raw GEE stats into actionable impact statements.

"523 km² flooded" → "3.2 lakh people affected, 12 schools, 3 hospitals, 42 km roads"

Sources:
  - WorldPop: population within affected polygon (REST API + GEE fallback)
  - OSM Overpass: school/hospital/road counts
  - Both cached aggressively to protect rate limits
"""
import structlog
from dataclasses import dataclass

from integrations.worldpop import WorldPopClient
from integrations.overpass import OverpassClient

log = structlog.get_logger(__name__)


@dataclass
class EnrichedContext:
    """Enrichment output appended to flood/erosion ThemeResults."""
    population_affected: int
    population_label: str            # "3.2 lakh", "1.4M", etc.
    schools_at_risk: int
    hospitals_at_risk: int
    roads_km_affected: float
    trajectories: list[dict]         # [{asset, type, years_to_impact}]

    def to_dict(self) -> dict:
        return {
            "population_affected": self.population_affected,
            "population_label": self.population_label,
            "schools_at_risk": self.schools_at_risk,
            "hospitals_at_risk": self.hospitals_at_risk,
            "roads_km_affected": round(self.roads_km_affected, 1),
            "trajectories": self.trajectories,
        }


class EnrichmentService:
    """Wraps WorldPop and OSM Overpass calls with caching."""

    def __init__(self) -> None:
        self._worldpop = WorldPopClient()
        self._overpass = OverpassClient()

    def enrich_flood(
        self,
        aoi_geojson: dict,
        flood_stats: dict,
    ) -> dict:
        """
        Enrich a flood result with population and infrastructure counts.
        Uses the flood extent polygon (or AOI bbox as fallback).
        """
        bbox = self._geojson_to_bbox(aoi_geojson)
        if not bbox:
            return {}

        pop = self._worldpop.get_population(bbox) or 0
        infra = self._overpass.get_infrastructure(bbox)

        return EnrichedContext(
            population_affected=pop,
            population_label=self._format_population(pop),
            schools_at_risk=infra.get("schools", 0),
            hospitals_at_risk=infra.get("hospitals", 0),
            roads_km_affected=infra.get("roads_km", 0.0),
            trajectories=[],
        ).to_dict()

    def enrich_erosion(
        self,
        aoi_geojson: dict,
        erosion_stats: dict,
        osm_assets: list[dict] | None = None,
    ) -> dict:
        """
        Enrich erosion result: infrastructure timeline within 500m of coast.
        Trajectories are computed in trajectory.py using erosion EPR.
        """
        bbox = self._geojson_to_bbox(aoi_geojson)
        if not bbox:
            return {}

        pop = self._worldpop.get_population(bbox) or 0
        infra = self._overpass.get_infrastructure(bbox)
        coastal_assets = self._overpass.get_coastal_assets(bbox, buffer_m=1000)

        mean_epr = erosion_stats.get("mean_epr_m_yr", 0)
        trajectories = []
        if mean_epr < 0:
            from services.trajectory import TrajectoryCalculator
            calc = TrajectoryCalculator()
            trajectories = calc.compute(coastal_assets, abs(mean_epr))

        return EnrichedContext(
            population_affected=pop,
            population_label=self._format_population(pop),
            schools_at_risk=infra.get("schools", 0),
            hospitals_at_risk=infra.get("hospitals", 0),
            roads_km_affected=infra.get("roads_km", 0.0),
            trajectories=trajectories,
        ).to_dict()

    def enrich_mangrove(
        self,
        aoi_geojson: dict,
        mangrove_stats: dict,
    ) -> dict:
        """Count coastal villages within 5km of mangrove extent (storm protection)."""
        bbox = self._geojson_to_bbox(aoi_geojson)
        if not bbox:
            return {}
        coastal_settlements = self._overpass.get_coastal_assets(bbox, buffer_m=5000)
        village_count = sum(
            1 for a in coastal_settlements
            if a.get("type") in ("settlement", "village", "town")
        )
        return {
            "coastal_villages_protected": village_count,
            "storm_protection_label": (
                f"{village_count} coastal settlements within mangrove buffer"
                if village_count > 0 else "No settlements in mangrove buffer"
            ),
        }

    @staticmethod
    def _geojson_to_bbox(geojson: dict) -> list[float] | None:
        """Extract [min_lon, min_lat, max_lon, max_lat] from GeoJSON."""
        try:
            from shapely.geometry import shape
            geom = shape(
                geojson.get("geometry", geojson)
                if geojson.get("type") == "Feature"
                else geojson
            )
            return list(geom.bounds)  # (minx, miny, maxx, maxy)
        except Exception as exc:
            log.warning("enrichment.bbox_error", error=str(exc))
            return None

    @staticmethod
    def _format_population(count: int) -> str:
        """Format population as South-Asian lakh or millions depending on scale."""
        if count >= 10_000_000:
            return f"{count / 1_000_000:.1f}M"
        elif count >= 100_000:
            lakh = count / 100_000
            return f"{lakh:.1f} lakh"
        elif count >= 1000:
            return f"{count / 1000:.1f}k"
        return str(count)
