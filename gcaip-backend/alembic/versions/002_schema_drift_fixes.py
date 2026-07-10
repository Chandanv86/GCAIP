"""Add missing columns: theme_results.error_class, risk_scores.water_sanitation_pressure
and risk_scores.infrastructure_integrity, plus the partial index on alerts.

Background
----------
Migration 001_initial created all five core tables but was written before three
subsequent model-level additions were made:

  1. models/theme_result.py   — added error_class (String 64, nullable)
  2. models/risk_score.py     — added water_sanitation_pressure (Float, nullable)
                                added infrastructure_integrity  (Float, nullable)
  3. models/alert.py          — added idx_alerts_active partial index on status/severity

No Alembic migration was ever written for any of these.  Alembic therefore still
considers the database at (head), hiding the drift completely.

Revision ID: 002_schema_drift_fixes
Revises:     001_initial
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "002_schema_drift_fixes"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. theme_results.error_class ────────────────────────────────────────
    # The model added this column for structured error classification
    # (e.g. GEEQuotaError, TimeoutError).  It is 100% nullable so the ADD
    # is safe against existing rows — Postgres fills them with NULL.
    op.add_column(
        "theme_results",
        sa.Column("error_class", sa.String(64), nullable=True),
    )

    # ── 2. risk_scores.water_sanitation_pressure ─────────────────────────────
    # New theme score component added as part of the water-sanitation theme work.
    op.add_column(
        "risk_scores",
        sa.Column("water_sanitation_pressure", sa.Float(), nullable=True),
    )

    # ── 3. risk_scores.infrastructure_integrity ──────────────────────────────
    # New theme score component added alongside water_sanitation_pressure.
    op.add_column(
        "risk_scores",
        sa.Column("infrastructure_integrity", sa.Float(), nullable=True),
    )

    # ── 4. alerts — partial index on (status, severity) WHERE active ─────────
    # The SQLAlchemy model declares this via __table_args__ but the initial
    # migration only called op.create_index without the postgresql_where clause.
    op.create_index(
        "idx_alerts_active",
        "alerts",
        ["status", "severity"],
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    # Reverse in opposite order
    op.drop_index("idx_alerts_active", table_name="alerts")
    op.drop_column("risk_scores", "infrastructure_integrity")
    op.drop_column("risk_scores", "water_sanitation_pressure")
    op.drop_column("theme_results", "error_class")
