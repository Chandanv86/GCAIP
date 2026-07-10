import json
import logging

from workers.celery_app import celery_app
from db.utils import get_sync_session as _get_sync_session

import structlog
log = structlog.get_logger(__name__)


def _publish_event(run_id: str, event: dict) -> None:
    import redis as redis_lib
    from config import settings
    r = redis_lib.from_url(settings.REDIS_URL)
    r.publish(f"gcaip:sse:{run_id}", json.dumps(event, default=str))


@celery_app.task(name="workers.tasks.enrichment_tasks.compute_risk_score_task",
                 queue="enrichment_tasks", max_retries=2)
def compute_risk_score_task(run_id: str) -> dict:
    """
    Aggregate all theme results for a run and compute composite risk score.
    Triggered automatically when all 7 theme tasks complete.
    """
    from models.theme_result import ThemeResult as ThemeResultModel
    from models.analysis_run import AnalysisRun
    from services.enrichment import EnrichmentService
    from services.risk_engine import RiskEngine
    from services.cross_theme import CrossThemeCorrelator

    session = _get_sync_session()
    try:
        # Load all theme results for this run
        theme_results = (
            session.query(ThemeResultModel)
            .filter_by(run_id=run_id)
            .all()
        )
        results_by_theme = {r.theme: r for r in theme_results}

        # Load run + AOI
        run = session.query(AnalysisRun).filter_by(id=run_id).first()
        if not run:
            log.error("risk_task.run_not_found", run_id=run_id)
            return {}

        # Load AOI GeoJSON for enrichment
        from geoalchemy2.shape import to_shape
        import json as _json
        aoi_shape = to_shape(run.aoi.geom)
        if hasattr(aoi_shape, "__geo_interface__"):
            aoi_geojson = aoi_shape.__geo_interface__
        else:
            from shapely.geometry import mapping
            aoi_geojson = mapping(aoi_shape)

        # ── Enrichment: WorldPop + OSM ────────────────────────────────────────
        enrichment_svc = EnrichmentService()
        flood_result = results_by_theme.get("flood")
        erosion_result = results_by_theme.get("erosion")

        enrichment = {}
        try:
            if flood_result and flood_result.stats.get("is_active"):
                enrichment = enrichment_svc.enrich_flood(
                    aoi_geojson=aoi_geojson,
                    flood_stats=flood_result.stats,
                )
                # Update enrichment on flood result
                flood_result.enrichment = enrichment
                session.commit()
        except Exception as enrich_exc:
            log.warning("risk_task.enrichment_error", error=str(enrich_exc))

        # ── Cross-theme correlation ───────────────────────────────────────────
        correlator = CrossThemeCorrelator()
        cross_insights = correlator.evaluate(
            {t: r.stats for t, r in results_by_theme.items() if r.stats}
        )

        # ── Risk score ────────────────────────────────────────────────────────
        engine = RiskEngine()
        risk_score = engine.compute(results_by_theme)

        # Store risk score
        from models.risk_score import RiskScore
        from datetime import datetime, timezone

        rs = RiskScore(
            run_id=run.id,
            aoi_id=run.aoi_id,
            overall_score=risk_score.overall_score,
            overall_label=risk_score.overall_label,
            flood_risk=risk_score.flood_risk,
            erosion_risk=risk_score.erosion_risk,
            water_stress=risk_score.water_stress,
            vegetation_health=risk_score.vegetation_health,
            landuse_pressure=risk_score.landuse_pressure,
            water_sanitation_pressure=risk_score.water_sanitation_pressure,
            infrastructure_integrity=risk_score.infrastructure_integrity,
            cross_insights=[ci.to_dict() for ci in cross_insights],
            population_in_aoi=enrichment.get("population_affected"),
            population_at_risk=enrichment.get("population_affected"),
        )
        session.add(rs)

        # Mark run as complete
        run.status = "complete"
        run.completed_at = datetime.now(timezone.utc)
        session.commit()

        # Publish risk score to SSE
        _publish_event(run_id, {
            "event": "risk_score",
            "score": {
                "overall_score": risk_score.overall_score,
                "overall_label": risk_score.overall_label,
                "flood_risk": risk_score.flood_risk,
                "erosion_risk": risk_score.erosion_risk,
                "water_stress": risk_score.water_stress,
                "vegetation_health": risk_score.vegetation_health,
                "landuse_pressure": risk_score.landuse_pressure,
                "water_sanitation_pressure": risk_score.water_sanitation_pressure,
                "infrastructure_integrity": risk_score.infrastructure_integrity,
                "cross_insights": [ci.to_dict() for ci in cross_insights],
            },
        })
        _publish_event(run_id, {
            "event": "analysis_complete",
            "run_id": run_id,
        })

        # Check alert thresholds (Phase 2)
        from workers.tasks.alert_tasks import evaluate_alerts_task
        evaluate_alerts_task.delay(run_id)

        return {"run_id": run_id, "overall_score": risk_score.overall_score}

    except Exception as exc:
        log.error("risk_task.error", run_id=run_id, error=str(exc))
        session.rollback()
        _publish_event(run_id, {"event": "error", "message": str(exc)})
        raise
    finally:
        session.close()
