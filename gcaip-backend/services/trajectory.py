"""
Trajectory Calculator — "Road N3 affected in 4 years at current erosion rate"

Takes OSM coastal assets + EPR rate → computes years_to_impact per asset.
"""
import structlog

log = structlog.get_logger(__name__)


class TrajectoryCalculator:
    """Extrapolates time-to-impact for coastal infrastructure given erosion rate."""

    def compute(
        self,
        coastal_assets: list[dict],
        erosion_rate_m_yr: float,  # Always positive (magnitude)
    ) -> list[dict]:
        """
        Args:
            coastal_assets: List of dicts from OSM Overpass, each with
                            {name, type, distance_m (from current shoreline)}
            erosion_rate_m_yr: EPR magnitude in m/yr (positive)

        Returns:
            List of trajectory dicts sorted by years_to_impact ascending
        """
        if erosion_rate_m_yr <= 0:
            return []

        trajectories = []
        for asset in coastal_assets:
            dist_m = asset.get("distance_m", 0)
            if dist_m <= 0:
                continue
            years = dist_m / erosion_rate_m_yr
            trajectories.append({
                "asset": asset.get("name", "Unnamed asset"),
                "type": asset.get("type", "unknown"),
                "distance_m": round(dist_m, 0),
                "years_to_impact": round(years, 1),
                "impact_year": (
                    __import__("datetime").date.today().year + int(years)
                ),
            })

        return sorted(trajectories, key=lambda t: t["years_to_impact"])
