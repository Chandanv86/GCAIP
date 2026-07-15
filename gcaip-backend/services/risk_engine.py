"""docstring"""
import structlog
from dataclasses import dataclass, field

log = structlog.get_logger(__name__)

# 7-theme weight distribution (sums to 1.0).
# Diagnostic report Section 5 starting point — tune after real runs.
WEIGHTS = {
    "flood":             0.20,   # flood extent + active flag
    "erosion":           0.15,   # shoreline EPR + storm wave risk
    "water_stress":      0.20,   # reservoir + rainfall + pollution cross-link
    "landuse":           0.15,   # land use pressure + pipeline encroachment
    "vegetation":        0.10,   # inverted vegetation health
    "water_sanitation": 0.12,   # effluent_plume + coastal_outfall anomaly
    "infrastructure":   0.08,   # pipeline corridor disturbance
}

assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, f"WEIGHTS must sum to 1.0, got {sum(WEIGHTS.values())}"


@dataclass
class RiskScore:
    overall_score: float
    overall_label: str  # LOW|MODERATE|HIGH|CRITICAL
    flood_risk: float | None
    erosion_risk: float | None
    water_stress: float | None
    vegetation_health: float | None
    landuse_pressure: float | None
    water_sanitation_pressure: float | None = None
    infrastructure_integrity: float | None = None
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
        # ── Sub-indices for all active themes ────────────────────────────────────
        flood_risk = self._flood_risk_index(results_by_theme.get("flood"))
        erosion_risk = self._erosion_risk_index(results_by_theme.get("erosion"))
        vegetation_health = self._vegetation_health_index(results_by_theme.get("vegetation"))
        water_stress = self._water_stress_index(
            results_by_theme.get("reservoir"),
            results_by_theme.get("rainfall"),
            results_by_theme.get("effluent_plume"),
            results_by_theme.get("coastal_outfall"),
        )
        landuse_pressure = self._landuse_pressure_index(
            results_by_theme.get("landuse"),
            results_by_theme.get("pipeline_corridor"),
        )
        water_sanitation_pressure = self._pollution_risk_index(
            results_by_theme.get("effluent_plume"),
            results_by_theme.get("coastal_outfall"),
        )
        infrastructure_integrity = self._infrastructure_integrity_index(
            results_by_theme.get("pipeline_corridor"),
        )

        # ── Composite overall score ─────────────────────────────────────────
        # 7 weighted sub-indices. See WEIGHTS at module top.
        overall = (
            flood_risk            * WEIGHTS["flood"]
            + erosion_risk        * WEIGHTS["erosion"]
            + water_stress        * WEIGHTS["water_stress"]
            + landuse_pressure    * WEIGHTS["landuse"]
            + vegetation_health   * WEIGHTS["vegetation"]
            + water_sanitation_pressure * WEIGHTS["water_sanitation"]
            + infrastructure_integrity  * WEIGHTS["infrastructure"]
        )
        overall = min(100.0, max(0.0, overall))

        log.debug(
            "risk_engine.computed",
            overall=round(overall, 1),
            flood_risk=round(flood_risk, 1),
            erosion_risk=round(erosion_risk, 1),
            water_stress=round(water_stress, 1),
            landuse_pressure=round(landuse_pressure, 1),
            vegetation_health=round(vegetation_health, 1),
            water_sanitation=round(water_sanitation_pressure, 1),
            infrastructure=round(infrastructure_integrity, 1),
        )

        return RiskScore(
            overall_score=round(overall, 1),
            overall_label=self._label(overall),
            flood_risk=round(flood_risk, 1),
            erosion_risk=round(erosion_risk, 1),
            water_stress=round(water_stress, 1),
            vegetation_health=round(vegetation_health, 1),
            landuse_pressure=round(landuse_pressure, 1),
            water_sanitation_pressure=round(water_sanitation_pressure, 1),
            infrastructure_integrity=round(infrastructure_integrity, 1),
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
    def _water_stress_index(
        reservoir_result,
        rainfall_result,
        effluent_result=None,
        coastal_result=None,
    ) -> float:
        """Water stress = reservoir fill anomaly + rainfall anomaly combined, lightly factoring in pollution anomaly (15%)."""
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

        # Cross-link: effluent plume / coastal outfall anomaly scores (weighted at 15% of water stress)
        pollution_score = 0.0
        pollution_cnt = 0
        if effluent_result and effluent_result.status == "complete":
            pollution_score += effluent_result.anomaly_score or 0.0
            pollution_cnt += 1
        if coastal_result and coastal_result.status == "complete":
            pollution_score += coastal_result.anomaly_score or 0.0
            pollution_cnt += 1

        if pollution_cnt > 0:
            avg_pollution = pollution_score / pollution_cnt
            score = (score * 0.85) + (avg_pollution * 0.15)

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
    def _landuse_pressure_index(result, pipeline_result=None) -> float:
        """Land use change → runoff increase + area changed. Factors in pipeline corridor encroachment if present."""
        if not result or result.status != "complete":
            return 0.0
        runoff_pct = result.stats.get("runoff_increase_pct", 0) or 0
        changed_ha = result.stats.get("changed_area_ha", 0) or 0
        # Runoff increase >20% = 60 points; changed area contributes rest
        score = min(60.0, runoff_pct / 20.0 * 60.0)
        score += min(40.0, changed_ha / 500.0 * 40.0)

        # Cross-link: pipeline corridor Dynamic World encroachment overlaps
        if pipeline_result and pipeline_result.status == "complete":
            pipeline_encroachment = pipeline_result.stats.get("encroachment_ha", 0.0) or 0.0
            encroachment_penalty = min(20.0, (pipeline_encroachment / 10.0) * 20.0)
            score = min(100.0, score + encroachment_penalty)

        return min(100.0, score)

    @staticmethod
    def _pollution_risk_index(effluent_result, coastal_result) -> float:
        """0-100 pollution risk. Combines effluent plume + coastal outfall anomaly scores."""
        scores = []
        if effluent_result and effluent_result.status == "complete":
            scores.append(effluent_result.anomaly_score or 0.0)
        if coastal_result and coastal_result.status == "complete":
            scores.append(coastal_result.anomaly_score or 0.0)
        return max(scores) if scores else 0.0

    @staticmethod
    def _infrastructure_integrity_index(pipeline_result) -> float:
        """0-100 infrastructure integrity score (inverted, higher = more disturbed/at risk)."""
        if not pipeline_result or pipeline_result.status != "complete":
            return 0.0
        return pipeline_result.anomaly_score or 0.0

    @staticmethod
    def _label(score: float) -> str:
        if score <= 25:
            return "LOW"
        elif score <= 50:
            return "MODERATE"
        elif score <= 75:
            return "HIGH"
        return "CRITICAL"
