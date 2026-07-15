"""
Alert Engine — evaluates risk thresholds and creates Alert records.
Deduplication via dedup_key prevents repeat alerts on consecutive runs.
"""
import structlog
from datetime import date, datetime, timedelta, timezone

log = structlog.get_logger(__name__)

# Alert thresholds
THRESHOLDS = {
    "flood_active": {
        "condition": lambda s: s.get("is_active", False),
        "severity": "WARNING",
        "alert_type": "flood_detected",
        "title_tpl": "FLOOD WARNING: {aoi_name}",
        "message_tpl": "{flooded_km2:.0f} km² flood extent detected.",
        "confidence_min": 0.6,
    },
    "spillway_risk": {
        "condition": lambda s: s.get("spillway_risk") in ("HIGH", "CRITICAL"),
        "severity": "WARNING",
        "alert_type": "spillway_risk",
        "title_tpl": "SPILLWAY RISK: {aoi_name}",
        "message_tpl": "Reservoir {fill_fraction_pct:.0f}% full, spillway risk elevated.",
        "confidence_min": 0.5,
    },
    "erosion_storm": {
        "condition": lambda s: (
            s.get("mean_epr_m_yr", 0) < -2.0
            and s.get("storm_wave_risk") == "HIGH"
        ),
        "severity": "WATCH",
        "alert_type": "erosion_storm_risk",
        "title_tpl": "EROSION + STORM RISK: {aoi_name}",
        "message_tpl": "Shoreline retreating {mean_epr_m_yr:.1f} m/yr + storm wave HIGH.",
        "confidence_min": 0.5,
    },
    "mangrove_loss": {
        "condition": lambda s: s.get("net_change_ha", 0) < -100,
        "severity": "WATCH",
        "alert_type": "mangrove_loss",
        "title_tpl": "MANGROVE LOSS: {aoi_name}",
        "message_tpl": "Net mangrove loss {net_change_ha:.0f} ha vs baseline.",
        "confidence_min": 0.55,
    },
    "extreme_rainfall": {
        "condition": lambda s: s.get("spi_7", 0) >= 2.0,
        "severity": "WATCH",
        "alert_type": "extreme_rainfall",
        "title_tpl": "EXTREME RAINFALL: {aoi_name}",
        "message_tpl": "SPI-7 = {spi_7:.1f} (Extremely Wet). Flash flood risk elevated.",
        "confidence_min": 0.7,
    },
    "effluent_plume_detected": {
        "condition": lambda s: s.get("plume_extent_km2", 0) >= 0.5,
        "severity": "WATCH",
        "alert_type": "effluent_plume_detected",
        "title_tpl": "EFFLUENT DISCHARGE PLUME: {aoi_name}",
        "message_tpl": "Wastewater/industrial effluent discharge plume of {plume_extent_km2:.1f} km² detected.",
        "confidence_min": 0.6,
    },
    "thermal_plume_active": {
        "condition": lambda s: s.get("thermal_plume_flag", False) is True,
        "severity": "WATCH",
        "alert_type": "thermal_plume_active",
        "title_tpl": "THERMAL DISCHARGE PLUME: {aoi_name}",
        "message_tpl": "SST anomaly of +{delta_sst_c:.1f}°C detected at outfall, thermal plume active.",
        "confidence_min": 0.6,
    },
    "spm_spike": {
        "condition": lambda s: s.get("spm_mean", 0) >= 20.0,
        "severity": "WATCH",
        "alert_type": "spm_spike",
        "title_tpl": "OUTFALL TURBIDITY SPIKE: {aoi_name}",
        "message_tpl": "Suspended particulate matter (SPM) at coastal outfall reached {spm_mean:.1f} mg/L.",
        "confidence_min": 0.6,
    },
    "corridor_encroachment": {
        "condition": lambda s: s.get("encroachment_ha", 0) >= 5.0,
        "severity": "WARNING",
        "alert_type": "corridor_encroachment",
        "title_tpl": "PIPELINE CORRIDOR ENCROACHMENT: {aoi_name}",
        "message_tpl": "Potential unauthorized encroachment of {encroachment_ha:.1f} ha detected inside pipeline corridor.",
        "confidence_min": 0.7,
    },
    "corridor_disturbance": {
        "condition": lambda s: s.get("disturbed_corridor_length_m", 0) >= 5000.0,
        "severity": "WATCH",
        "alert_type": "corridor_disturbance",
        "title_tpl": "PIPELINE CORRIDOR DISTURBANCE: {aoi_name}",
        "message_tpl": "Pipeline corridor disturbed length has reached {disturbed_corridor_length_m:.0f} meters.",
        "confidence_min": 0.6,
    },
    "oil_sheen_detected": {
        "condition": lambda s: s.get("oil_sheen_km2", 0) >= 0.05,
        "severity": "WARNING",
        "alert_type": "oil_sheen_detected",
        "title_tpl": "POSSIBLE OIL/SURFACTANT SHEEN: {aoi_name}",
        "message_tpl": "SAR surface-dampening consistent with an oil sheen detected over {oil_sheen_km2:.2f} km².",
        "confidence_min": 0.5,
    },
}


class AlertEngine:
    """Evaluates thresholds and upserts Alert records with deduplication."""

    def evaluate(
        self,
        aoi_id: str,
        run_id: str,
        theme_results: dict,
        session,
    ) -> list:
        """
        Args:
            aoi_id: UUID string
            run_id: UUID string
            theme_results: dict[theme_name → ThemeResult ORM object]
            session: SQLAlchemy sync session

        Returns:
            List of newly created Alert objects
        """
        from models.alert import Alert
        from models.aoi import AOI

        aoi = session.query(AOI).filter_by(id=aoi_id).first()
        aoi_name = aoi.name or aoi_id if aoi else aoi_id
        # P7 fix: use UTC date for dedup_key to avoid timezone-drift duplicates near midnight.
        # Previously used date.today() (local server time), which could differ from the
        # UTC timestamps on alert records, causing duplicates at midnight boundaries.
        today_utc = datetime.now(timezone.utc).date().isoformat()
        created = []

        # Map theme → applicable rules (only active themes)
        theme_rule_map = {
            "flood": ["flood_active"],
            "rainfall": ["extreme_rainfall"],
            "reservoir": ["spillway_risk"],
            "erosion": ["erosion_storm"],
            "vegetation": [],          # no alert rule yet — runs but fires no alerts
            "mangrove": ["mangrove_loss"],
            "landuse": [],             # monitored in risk_engine; no standalone alert rule
            "effluent_plume": ["effluent_plume_detected"],
            "coastal_outfall": ["thermal_plume_active", "spm_spike", "oil_sheen_detected"],
            "pipeline_corridor": ["corridor_encroachment", "corridor_disturbance"],
        }

        for theme_name, rule_ids in theme_rule_map.items():
            result = theme_results.get(theme_name)
            if not result or result.status != "complete":
                continue
            if (result.confidence or 0) < 0.4:
                continue  # Too uncertain to alert

            stats = result.stats or {}

            for rule_id in rule_ids:
                rule = THRESHOLDS.get(rule_id)
                if not rule:
                    continue
                if (result.confidence or 0) < rule["confidence_min"]:
                    continue

                try:
                    triggered = rule["condition"](stats)
                except Exception:
                    triggered = False

                if not triggered:
                    continue

                dedup_key = f"{aoi_id}:{rule['alert_type']}:{today_utc}"

                # Skip if already alerted today
                existing = session.query(Alert).filter_by(dedup_key=dedup_key).first()
                if existing:
                    log.info("alert_engine.dedup_skip", dedup_key=dedup_key)
                    continue

                try:
                    title = rule["title_tpl"].format(aoi_name=aoi_name, **stats)
                    message = rule["message_tpl"].format(**stats)
                except (KeyError, ValueError) as fmt_exc:
                    log.warning("alert_engine.fmt_error", error=str(fmt_exc))
                    title = rule["title_tpl"].split(":")[0] + f": {aoi_name}"
                    message = f"Threshold breached for {theme_name}."

                alert = Alert(
                    aoi_id=aoi_id,
                    severity=rule["severity"],
                    theme=theme_name,
                    alert_type=rule["alert_type"],
                    title=title,
                    message=message,
                    metric_value=result.metric_value,
                    metric_unit=result.metric_unit,
                    tile_url=result.tile_url,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                    dedup_key=dedup_key,
                )
                session.add(alert)
                created.append(alert)
                log.info(
                    "alert_engine.alert_created",
                    alert_type=rule["alert_type"],
                    aoi_id=aoi_id,
                    severity=rule["severity"],
                )

        if created:
            session.commit()
        return created
