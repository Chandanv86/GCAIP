"""
PDF Report Generation — converts a completed analysis run into a
client-ready PDF using WeasyPrint (HTML → PDF).
"""
import logging
import os
from datetime import datetime, timezone

from workers.celery_app import celery_app

import structlog
log = structlog.get_logger(__name__)

REPORT_OUTPUT_DIR = "/tmp/gcaip_reports"


def _get_sync_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from config import settings
    sync_url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    )
    engine = create_engine(sync_url, pool_pre_ping=True)
    return sessionmaker(bind=engine)()


@celery_app.task(name="workers.tasks.report_tasks.generate_report_task",
                 queue="default", max_retries=2)
def generate_report_task(run_id: str) -> dict:
    """
    Build an HTML report from the analysis run, render to PDF via WeasyPrint,
    save to local disk (Phase 2: upload to S3/GCS for download links).
    """
    from models.analysis_run import AnalysisRun
    from models.theme_result import ThemeResult
    from models.risk_score import RiskScore

    os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)

    session = _get_sync_session()
    try:
        run = session.query(AnalysisRun).filter_by(id=run_id).first()
        if not run:
            return {"error": "Run not found"}

        themes = session.query(ThemeResult).filter_by(run_id=run_id).all()
        risk = session.query(RiskScore).filter_by(run_id=run_id).first()

        html_content = _build_html(run, themes, risk)

        try:
            from weasyprint import HTML
            output_path = f"{REPORT_OUTPUT_DIR}/gcaip_report_{run_id}.pdf"
            HTML(string=html_content).write_pdf(output_path)
            log.info("report_task.generated", path=output_path)
            return {"status": "complete", "path": output_path}
        except Exception as pdf_exc:
            log.error("report_task.pdf_error", error=str(pdf_exc))
            return {"status": "failed", "error": str(pdf_exc)}
    finally:
        session.close()


def _build_html(run, themes, risk) -> str:
    """Build the report HTML — kept simple and print-friendly."""
    theme_rows = ""
    for t in sorted(themes, key=lambda x: x.theme):
        theme_rows += f"""
        <tr>
            <td>{t.theme.title()}</td>
            <td>{t.metric_label or '—'}</td>
            <td>{(t.confidence or 0) * 100:.0f}%</td>
            <td>{t.data_source or '—'}</td>
        </tr>
        """

    insights_html = ""
    if risk and risk.cross_insights:
        for ci in risk.cross_insights:
            insights_html += f"""
            <div class="insight {ci.get('severity', 'INFO').lower()}">
                <strong>{ci.get('severity')}</strong>: {ci.get('insight_text')}
                <p><em>Recommended action:</em> {ci.get('recommended_action')}</p>
            </div>
            """

    risk_section = ""
    if risk:
        risk_section = f"""
        <h2>Composite Risk Score: {risk.overall_score:.0f}/100 ({risk.overall_label})</h2>
        <table>
            <tr><td>Flood Risk</td><td>{risk.flood_risk or 0:.0f}/100</td></tr>
            <tr><td>Erosion Risk</td><td>{risk.erosion_risk or 0:.0f}/100</td></tr>
            <tr><td>Water Stress</td><td>{risk.water_stress or 0:.0f}/100</td></tr>
            <tr><td>Vegetation Health</td><td>{risk.vegetation_health or 0:.0f}/100</td></tr>
            <tr><td>Land Use Pressure</td><td>{risk.landuse_pressure or 0:.0f}/100</td></tr>
        </table>
        """

    return f"""
    <html>
    <head>
    <style>
        body {{ font-family: 'Helvetica', sans-serif; margin: 40px; color: #1a1a1a; }}
        h1 {{ color: #0d47a1; border-bottom: 3px solid #0d47a1; padding-bottom: 10px; }}
        h2 {{ color: #1a5276; margin-top: 30px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background: #f2f2f2; }}
        .insight {{ border-left: 4px solid #888; padding: 10px; margin: 10px 0; background: #fafafa; }}
        .insight.warning {{ border-color: #e65100; }}
        .insight.emergency {{ border-color: #b71c1c; }}
        .insight.watch {{ border-color: #f9a825; }}
        .footer {{ margin-top: 40px; font-size: 11px; color: #888; }}
    </style>
    </head>
    <body>
        <h1>GCAIP Climate Adaptation Report</h1>
        <p><strong>Analysis Period:</strong> {run.date_range_start} to {run.date_range_end}</p>
        <p><strong>Generated:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>

        {risk_section}

        <h2>Cross-Theme Insights</h2>
        {insights_html or '<p>No compound risk patterns detected.</p>'}

        <h2>Theme Results</h2>
        <table>
            <tr><th>Theme</th><th>Finding</th><th>Confidence</th><th>Data Source</th></tr>
            {theme_rows}
        </table>

        <div class="footer">
            Generated by GCAIP — Geospatial Climate Adaptation Intelligence Platform.
            Data sourced from Google Earth Engine (Sentinel-1, Sentinel-2, GPM IMERG,
            CHIRPS, JRC, Dynamic World, ESA WorldCover). For decision-support use only;
            verify with ground-truth data before emergency action.
        </div>
    </body>
    </html>
    """
