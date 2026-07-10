#!/usr/bin/env python
"""
GCAIP — Schema Drift Guard
==========================
Compares the live database schema against every SQLAlchemy model and raises
a hard error if any column is present in the model but absent from the DB.

Usage
-----
Run manually before deploying:

    python scripts/check_schema.py

Or wire it into your CI pipeline:

    python scripts/check_schema.py && echo "Schema OK — safe to deploy"

Exit codes
----------
0  — all models match the live schema
1  — drift detected (missing columns listed); do NOT deploy until fixed

How it works
------------
1. Imports all SQLAlchemy models (same call used by Alembic env.py).
2. Connects to the live database using DATABASE_URL from .env / environment.
3. Uses SQLAlchemy's Inspector to reflect the actual table columns.
4. Compares every model column against the reflected schema — column by column.
5. Also checks that every expected index name exists (catches missing partial
   indexes like idx_alerts_active which have no column-level representation).
6. Prints a full drift report and exits non-zero if any drift is found.
"""
import sys
import os

# Allow running from the backend root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text
from db.base import Base, import_all_models
from config import settings

# ── Expected indexes per table (supplement column checks) ──────────────────
# Add any index that cannot be inferred from column presence alone
# (e.g. partial/conditional indexes).
EXPECTED_INDEXES: dict[str, list[str]] = {
    "alerts": ["idx_alerts_active"],
    "theme_results": ["idx_results_run", "idx_results_theme_time", "uq_run_theme"],
    "risk_scores": ["idx_risk_aoi_time"],
    "analysis_runs": ["idx_runs_aoi_time", "idx_runs_status"],
    "aois": ["idx_aois_geom", "idx_aois_user"],
    "users": ["idx_users_email"],
}


def _sync_url(url: str) -> str:
    """Convert asyncpg URL to psycopg2-compatible URL for synchronous inspection."""
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


def main() -> int:
    import_all_models()

    # Use a synchronous engine — Inspector requires synchronous connections.
    # Fall back to psycopg2 driver; psycopg2-binary is already in requirements.txt
    try:
        sync_url = _sync_url(settings.DATABASE_URL)
        engine = create_engine(sync_url, echo=False)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        print(f"[DRIFT-CHECK] ✗ Cannot connect to database: {exc}", file=sys.stderr)
        print("[DRIFT-CHECK]   Check DATABASE_URL in .env and that the DB is running.",
              file=sys.stderr)
        return 1

    inspector = inspect(engine)
    drift_found = False

    print("[DRIFT-CHECK] Comparing SQLAlchemy models -> live database schema ...\n")

    for table_name, table in Base.metadata.tables.items():
        # Reflect live columns
        try:
            live_cols = {
                col["name"]: col
                for col in inspector.get_columns(table_name)
            }
        except Exception:
            print(f"  [ERROR] Table '{table_name}' does not exist in the live database!")
            drift_found = True
            continue

        model_cols = {col.name: col for col in table.columns}

        # ── Column presence check ──────────────────────────────────────────
        missing = [c for c in model_cols if c not in live_cols]
        extra   = [c for c in live_cols  if c not in model_cols]

        if missing:
            drift_found = True
            for col in missing:
                model_col = model_cols[col]
                print(
                    f"  [ERROR] [{table_name}] MISSING column '{col}' "
                    f"(model type: {model_col.type})"
                )
        if extra:
            # Extra columns in DB are not a crash risk — warn only
            for col in extra:
                print(f"  [WARN] [{table_name}] Extra column in DB (not in model): '{col}'")

        if not missing and not extra:
            print(f"  [OK] {table_name} - columns OK ({len(model_cols)} columns)")

        # ── Index presence check ───────────────────────────────────────────
        expected_idxs = EXPECTED_INDEXES.get(table_name, [])
        if expected_idxs:
            live_idxs = {idx["name"] for idx in inspector.get_indexes(table_name)}
            # Also include unique constraints (listed separately by inspector)
            live_idxs |= {
                uc["name"]
                for uc in inspector.get_unique_constraints(table_name)
                if uc.get("name")
            }
            for idx_name in expected_idxs:
                if idx_name not in live_idxs:
                    drift_found = True
                    print(
                        f"  [ERROR] [{table_name}] MISSING index '{idx_name}' "
                        f"(defined in model __table_args__ but not in live DB)"
                    )

    engine.dispose()
    print()
    if drift_found:
        print(
            "[DRIFT-CHECK] [ERROR] SCHEMA DRIFT DETECTED - run 'alembic upgrade head' "
            "before deploying!\n"
            "              If no migration covers the missing items, write one first."
        )
        return 1
    else:
        print("[DRIFT-CHECK] [OK] All models match the live database schema. Safe to deploy.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
