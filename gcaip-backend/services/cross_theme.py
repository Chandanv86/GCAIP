"""
Cross-Theme Correlation Engine — detects compound risk when multiple themes combine.

"Reservoir 92% full + 7-day rainfall at 98th percentile = HIGH spillway risk"
"Mangrove loss reducing wave protection — erosion accelerating"

This is GCAIP's highest-value analytical layer. Each rule produces a
CrossInsight with severity and a plain-language recommended action.
"""
from dataclasses import dataclass, field


@dataclass
class CrossInsight:
    insight_id: str
    insight_text: str       # What is happening (plain language)
    severity: str           # INFO | WATCH | WARNING | EMERGENCY
    theme_ids: list[str]    # Which themes triggered this
    recommended_action: str # What should be done

    def to_dict(self) -> dict:
        return {
            "insight_id": self.insight_id,
            "insight_text": self.insight_text,
            "severity": self.severity,
            "theme_ids": self.theme_ids,
            "recommended_action": self.recommended_action,
        }


class CrossThemeCorrelator:
    """Evaluates compound risk rules across all 7 themes."""

    def evaluate(self, stats_by_theme: dict[str, dict]) -> list[CrossInsight]:
        """
        Args:
            stats_by_theme: {theme_name: stats_dict} from completed theme results

        Returns:
            List of CrossInsight objects, sorted by severity descending
        """
        insights: list[CrossInsight] = []

        flood = stats_by_theme.get("flood", {})
        rainfall = stats_by_theme.get("rainfall", {})
        reservoir = stats_by_theme.get("reservoir", {})
        erosion = stats_by_theme.get("erosion", {})
        mangrove = stats_by_theme.get("mangrove", {})
        landuse = stats_by_theme.get("landuse", {})
        vegetation = stats_by_theme.get("vegetation", {})

        # ── Rule 1: RESERVOIR + RAINFALL → SPILLWAY RISK ─────────────────────
        fill = reservoir.get("fill_fraction_pct", 0) or 0
        rain_pct = rainfall.get("percentile_7d", 0) or 0
        if fill > 85 and rain_pct > 90:
            severity = "WARNING" if fill > 95 or rain_pct > 97 else "WATCH"
            insights.append(CrossInsight(
                insight_id="spillway_risk",
                insight_text=(
                    f"Reservoir {fill:.0f}% full + 7-day rainfall at "
                    f"{rain_pct:.0f}th percentile → elevated spillway risk"
                ),
                severity=severity,
                theme_ids=["reservoir", "rainfall"],
                recommended_action=(
                    "Notify reservoir operators. Pre-position downstream evacuation "
                    "resources. Monitor spillway gates every 6 hours."
                ),
            ))

        # ── Rule 2: RAINFALL + LAND USE → RUNOFF AMPLIFICATION ───────────────
        runoff_pct = landuse.get("runoff_increase_pct", 0) or 0
        spi_7 = rainfall.get("spi_7", 0) or 0
        if spi_7 > 1.5 and runoff_pct > 10:
            insights.append(CrossInsight(
                insight_id="runoff_amplification",
                insight_text=(
                    f"Deforestation has increased catchment runoff by "
                    f"~{runoff_pct:.0f}% — flood peak amplified by land use change"
                ),
                severity="WATCH",
                theme_ids=["rainfall", "landuse"],
                recommended_action=(
                    "Alert watershed managers. Restrict upstream clearing operations. "
                    "Deploy temporary flood barriers in downstream settlements."
                ),
            ))

        # ── Rule 3: FLOOD + RESERVOIR → DOWNSTREAM RISK ──────────────────────
        is_active_flood = flood.get("is_active", False)
        if is_active_flood and fill > 90:
            insights.append(CrossInsight(
                insight_id="downstream_compound_risk",
                insight_text=(
                    f"Active flooding detected + reservoir at {fill:.0f}% capacity "
                    f"— downstream areas at elevated compound risk"
                ),
                severity="WARNING",
                theme_ids=["flood", "reservoir"],
                recommended_action=(
                    "Issue downstream flood warning. Activate emergency operations "
                    "centre. Evacuation of low-lying areas within 10km downstream."
                ),
            ))

        # ── Rule 4: EROSION + STORM → RAPID RETREAT RISK ─────────────────────
        epr = erosion.get("mean_epr_m_yr", 0) or 0
        storm_risk = erosion.get("storm_wave_risk", "LOW")
        if epr < -1.5 and storm_risk == "HIGH":
            insights.append(CrossInsight(
                insight_id="storm_erosion_compound",
                insight_text=(
                    f"Shoreline retreating {abs(epr):.1f} m/yr + storm wave "
                    f"forecast HIGH — acute rapid erosion risk in next 48-72h"
                ),
                severity="WARNING",
                theme_ids=["erosion"],
                recommended_action=(
                    "Relocate equipment/assets from beach areas immediately. "
                    "Restrict coastal access. Alert coastal engineering teams."
                ),
            ))

        # ── Rule 5: MANGROVE LOSS + EROSION → BUFFER COLLAPSE ────────────────
        net_change = mangrove.get("net_change_ha", 0) or 0
        if net_change < -50 and epr < -1.0:
            insights.append(CrossInsight(
                insight_id="buffer_collapse_risk",
                insight_text=(
                    f"Mangrove loss of {abs(net_change):.0f} ha is reducing "
                    f"natural wave protection — erosion rate likely accelerating"
                ),
                severity="WATCH",
                theme_ids=["mangrove", "erosion"],
                recommended_action=(
                    "Prioritise mangrove restoration in eroding coastal segments. "
                    "Install temporary wave-break structures where buffer < 100m."
                ),
            ))

        # ── Rule 6: FLOOD + HIGH RAINFALL → EXTENDED INUNDATION ─────────────
        if is_active_flood and spi_7 > 2.0:
            insights.append(CrossInsight(
                insight_id="extended_inundation_risk",
                insight_text=(
                    "Active flooding combined with extremely wet conditions "
                    f"(SPI-7: {spi_7:.1f}) — inundation likely to persist or deepen"
                ),
                severity="WARNING" if spi_7 > 2.5 else "WATCH",
                theme_ids=["flood", "rainfall"],
                recommended_action=(
                    "Do not stand down flood response. Prepare for 72h+ inundation. "
                    "Stockpile clean water and medicine in elevated staging areas."
                ),
            ))

        # Sort by severity: EMERGENCY > WARNING > WATCH > INFO
        severity_order = {"EMERGENCY": 0, "WARNING": 1, "WATCH": 2, "INFO": 3}
        insights.sort(key=lambda i: severity_order.get(i.severity, 99))
        return insights
