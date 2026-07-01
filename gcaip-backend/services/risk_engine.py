"""
Risk Score Engine — weighted composite of all 7 GEE theme results.

Weights:
  Flood Risk Index:      35%
  Erosion Risk Index:    20%
  Water Stress Index:    15%
  Vegetation Health:     15%
  Land Use Pressure:     15%

Score labels: 0-25=LOW, 26-50=MODERATE, 51-75=HIGH, 76-100=CRITICAL
"""
import structlog
from dataclasses import dataclass, field

log = structlog.get_logger(__name__)

WEIGHTS = {
    "water_stress": 0.50,   # rainfall (active)
    "landuse": 0.50,        # landuse (active)
}


@dataclass
class RiskScore:
    overall_score: float
    overall_label: str  # LOW|MODERATE|HIGH|CRITICAL
    flood_risk: float | None
    erosion_risk: float | None
    water_stress: float | None
    vegetation_health: float | None
    landuse_pressure: float | None
    cross_insights: list = field(default_factory=list)


class RiskEngine:
    """Computes composite climate risk score from theme results."""

    def compute(self, results_by_theme: dict) -> RiskScore:
        """
        Args:
            results_by_theme: dict mapping theme name → ThemeResult ORM model

        Returns:
            RiskScore dataclass
        """
        # Active themes only
        water_stress = self._water_stress_index(
            None,  # reservoir disabled
            results_by_theme.get("rainfall"),
        )
        landuse_pressure = self._landuse_pressure_index(results_by_theme.get("landuse"))

        overall = (
            water_stress * WEIGHTS["water_stress"]
            + landuse_pressure * WEIGHTS["landuse"]
        )
        overall = min(100.0, max(0.0, overall))

        return RiskScore(
            overall_score=round(overall, 1),
            overall_label=self._label(overall),
            flood_risk=None,
            erosion_risk=None,
            water_stress=round(water_stress, 1),
            vegetation_health=None,
            landuse_pressure=round(landuse_pressure, 1),
        )

    @staticmethod
    def _flood_risk_index(result) -> float:
        """0-100 flood risk. Combines: is_active flag + flooded_km2 + anomaly_score."""
        if not result or result.status != "complete":
            return 0.0
        stats = result.stats or {}
        score = result.anomaly_score or 0.0
        if stats.get("is_active"):
            score = max(score, 50.0)  # Any active flood = at least 50/100
        if stats.get("urban_flag"):
            score = min(100.0, score + 20.0)  # Urban flood = +20 penalty
        return score

    @staticmethod
    def _erosion_risk_index(result) -> float:
        """0-100 erosion risk. EPR more negative → higher score."""
        if not result or result.status != "complete":
            return 0.0
        epr = abs(result.stats.get("mean_epr_m_yr", 0) or 0)
        # 5+ m/yr = 100; scale linearly
        base = min(100.0, epr / 5.0 * 100.0)
        if result.stats.get("storm_wave_risk") == "HIGH":
            base = min(100.0, base + 25.0)
        return base

    @staticmethod
    def _water_stress_index(reservoir_result, rainfall_result) -> float:
        """Water stress = reservoir fill anomaly + rainfall anomaly combined."""
        score = 0.0
        if reservoir_result and reservoir_result.status == "complete":
            fill = reservoir_result.stats.get("fill_fraction_pct", 50) or 50
            # >90% fill = stress; <20% fill = drought stress
            if fill > 90:
                score += min(60.0, (fill - 90.0) / 10.0 * 60.0)
            elif fill < 20:
                score += min(40.0, (20.0 - fill) / 20.0 * 40.0)
        if rainfall_result and rainfall_result.status == "complete":
            spi = abs(rainfall_result.stats.get("spi_7", 0) or 0)
            score += min(40.0, spi / 3.0 * 40.0)
        return min(100.0, score)

    @staticmethod
    def _vegetation_health_index(result) -> float:
        """Inverted health: degraded vegetation = high risk."""
        if not result or result.status != "complete":
            return 0.0
        health = result.stats.get("health_score", 100) or 100
        base = 100.0 - health
        if result.stats.get("dieback_flag"):
            base = min(100.0, base + 20.0)
        return base

    @staticmethod
    def _landuse_pressure_index(result) -> float:
        """Land use change → runoff increase + area changed."""
        if not result or result.status != "complete":
            return 0.0
        runoff_pct = result.stats.get("runoff_increase_pct", 0) or 0
        changed_ha = result.stats.get("changed_area_ha", 0) or 0
        # Runoff increase >20% = 60 points; changed area contributes rest
        score = min(60.0, runoff_pct / 20.0 * 60.0)
        score += min(40.0, changed_ha / 500.0 * 40.0)
        return min(100.0, score)

    @staticmethod
    def _label(score: float) -> str:
        if score <= 25:
            return "LOW"
        elif score <= 50:
            return "MODERATE"
        elif score <= 75:
            return "HIGH"
        return "CRITICAL"
