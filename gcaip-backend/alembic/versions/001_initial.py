"""Initial schema — all 5 tables + TimescaleDB hypertable.

Revision ID: 001_initial
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- Enable PostGIS ----
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    # ---- users ----
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255)),
        sa.Column("hashed_password", sa.String(255)),
        sa.Column("is_verified", sa.Boolean(), default=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("tier", sa.String(32), default="free"),
        sa.Column("max_aoi_km2", sa.Float(), default=500.0),
        sa.Column("monthly_analysis_count", sa.Integer(), default=0),
        sa.Column("preferred_notification_email", sa.String(255)),
        sa.Column("timezone", sa.String(64), default="UTC"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("idx_users_email", "users", ["email"])

    # ---- aois ----
    op.create_table(
        "aois",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(512)),
        # PostGIS geometry columns
        sa.Column("geom", sa.Text(), nullable=False),   # handled by GeoAlchemy2
        sa.Column("bbox", sa.Text()),
        sa.Column("area_km2", sa.Float()),
        sa.Column("country_code", sa.String(2)),
        sa.Column("admin_level1", sa.String(256)),
        sa.Column("admin_level2", sa.String(256)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id")),
        sa.Column("is_public", sa.Boolean(), default=False),
        sa.Column("tags", postgresql.JSONB(), default={}),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
    )
    # Use raw SQL for PostGIS geometry columns (GeoAlchemy2 migrations)
    op.execute(
        "ALTER TABLE aois ALTER COLUMN geom TYPE geometry(POLYGON,4326) "
        "USING ST_GeomFromText(geom, 4326)"
    )
    op.execute(
        "ALTER TABLE aois ALTER COLUMN bbox TYPE geometry(POLYGON,4326) "
        "USING ST_GeomFromText(bbox, 4326)"
    )
    op.execute("CREATE INDEX idx_aois_geom ON aois USING GIST(geom)")
    op.create_index("idx_aois_user", "aois", ["created_by"])
    op.execute(
        "ALTER TABLE aois ADD CONSTRAINT max_area CHECK (area_km2 <= 50000)"
    )

    # ---- analysis_runs ----
    op.create_table(
        "analysis_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("aoi_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("aois.id"), nullable=False),
        sa.Column("status", sa.String(32), default="pending"),
        sa.Column("triggered_by", sa.String(32), default="user"),
        sa.Column("date_range_start", sa.Date(), nullable=False),
        sa.Column("date_range_end", sa.Date(), nullable=False),
        sa.Column("celery_task_id", sa.String(255)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("duration_sec", sa.Float()),
        sa.Column("error_message", sa.Text()),
        sa.Column("gee_quota_used", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_runs_aoi_time", "analysis_runs", ["aoi_id", "created_at"])
    op.create_index("idx_runs_status", "analysis_runs", ["status"])

    # ---- theme_results ----
    op.create_table(
        "theme_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("theme", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), default="pending"),
        sa.Column("tile_url", sa.Text()),
        sa.Column("tile_url_expires_at", sa.DateTime(timezone=True)),
        sa.Column("vis_params", postgresql.JSONB()),
        sa.Column("metric_value", sa.Float()),
        sa.Column("metric_unit", sa.String(32)),
        sa.Column("metric_label", sa.String(512)),
        sa.Column("stats", postgresql.JSONB(), default={}),
        sa.Column("enrichment", postgresql.JSONB(), default={}),
        sa.Column("anomaly_score", sa.Float()),
        sa.Column("confidence", sa.Float()),
        sa.Column("data_age_hours", sa.Float()),
        sa.Column("data_source", sa.String(512)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.UniqueConstraint("run_id", "theme", name="uq_run_theme"),
    )
    op.create_index("idx_results_run", "theme_results", ["run_id"])
    op.create_index("idx_results_theme_time", "theme_results", ["theme", "completed_at"])

    # ---- risk_scores ----
    op.create_table(
        "risk_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("analysis_runs.id"), nullable=False, unique=True),
        sa.Column("aoi_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("aois.id"), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("overall_label", sa.String(16), nullable=False),
        sa.Column("flood_risk", sa.Float()),
        sa.Column("erosion_risk", sa.Float()),
        sa.Column("water_stress", sa.Float()),
        sa.Column("vegetation_health", sa.Float()),
        sa.Column("landuse_pressure", sa.Float()),
        sa.Column("cross_insights", postgresql.JSONB(), default=[]),
        sa.Column("population_in_aoi", sa.BigInteger()),
        sa.Column("population_at_risk", sa.BigInteger()),
        sa.Column("scored_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_risk_aoi_time", "risk_scores", ["aoi_id", "scored_at"])

    # ---- alerts ----
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("aoi_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("aois.id"), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("theme", sa.String(64), nullable=False),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metric_value", sa.Float()),
        sa.Column("metric_unit", sa.String(32)),
        sa.Column("cross_insights", postgresql.JSONB(), default=[]),
        sa.Column("tile_url", sa.Text()),
        sa.Column("triggered_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(32), default="active"),
        sa.Column("dedup_key", sa.String(512), unique=True),
        sa.Column("email_sent", sa.Boolean(), default=False),
        sa.Column("push_sent", sa.Boolean(), default=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_alerts_aoi_time", "alerts", ["aoi_id", "triggered_at"])

    # ---- metric_timeseries (TimescaleDB hypertable) ----
    op.execute("""
        CREATE TABLE metric_timeseries (
            time          TIMESTAMPTZ NOT NULL,
            aoi_id        UUID NOT NULL,
            theme         TEXT NOT NULL,
            metric_name   TEXT NOT NULL,
            value         DOUBLE PRECISION,
            confidence    FLOAT,
            source        TEXT,
            flags         JSONB DEFAULT '{}'
        )
    """)
    op.execute(
        "SELECT create_hypertable('metric_timeseries', 'time')"
    )
    op.execute(
        "CREATE INDEX idx_ts_aoi_theme ON metric_timeseries(aoi_id, theme, time DESC)"
    )
    # Continuous aggregate: daily rollup
    op.execute("""
        CREATE MATERIALIZED VIEW metric_daily
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 day', time) AS day,
            aoi_id,
            theme,
            metric_name,
            avg(value)  AS avg_value,
            min(value)  AS min_value,
            max(value)  AS max_value,
            avg(confidence) AS avg_confidence
        FROM metric_timeseries
        GROUP BY day, aoi_id, theme, metric_name
        WITH NO DATA;
    """)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS metric_daily")
    op.execute("DROP TABLE IF EXISTS metric_timeseries")
    op.drop_table("alerts")
    op.drop_table("risk_scores")
    op.drop_table("theme_results")
    op.drop_table("analysis_runs")
    op.drop_table("aois")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS timescaledb")
    op.execute("DROP EXTENSION IF EXISTS postgis")
