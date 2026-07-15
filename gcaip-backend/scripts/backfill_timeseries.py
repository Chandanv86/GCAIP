#!/usr/bin/env python3
"""
scripts/backfill_timeseries.py

One-time backfill: populates metric_timeseries from all existing
theme_results rows that are status='complete'.

Diagnostic report reference: Section 6, item 5.

Run ONCE after deploying timeseries_writer.py to seed historical charts
from the theme_results rows that already exist. After this, the live
write path in _run_theme() keeps the table current for every new run.

Usage:
    cd gcaip-backend
    python scripts/backfill_timeseries.py [--dry-run] [--theme rainfall] [--limit 100]

The script is idempotent: re-running it will insert duplicate time-series
rows for the same (aoi_id, theme, time) key, which may inflate averages in
yearly trend queries. If you need to re-run it, truncate metric_timeseries
first or add a UNIQUE constraint -- see diagnostic report, Section 6, item 2.
"""
from __future__ import annotations

import argparse
import sys
from datetime import timezone

from sqlalchemy import text


def main():
    parser = argparse.ArgumentParser(description="Backfill metric_timeseries from theme_results")
    parser.add_argument("--dry-run", action="store_true", help="Print rows that would be written without writing")
    parser.add_argument("--theme", help="Only backfill this specific theme (e.g. 'rainfall')")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N theme_results rows (0 = no limit)")
    args = parser.parse_args()

    # Import here so the script can be run from gcaip-backend/
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    from db.utils import get_sync_session
    from services.timeseries_writer import write_theme_metrics

    session = get_sync_session()
    try:
        where_theme = f"AND tr.theme = '{args.theme}'" if args.theme else ""
        limit_clause = f"LIMIT {args.limit}" if args.limit > 0 else ""

        rows = session.execute(text(f"""
            SELECT
                tr.run_id,
                tr.theme,
                tr.stats,
                tr.metric_value,
                tr.confidence,
                tr.data_source,
                tr.completed_at,
                ar.aoi_id
            FROM theme_results tr
            JOIN analysis_runs ar ON ar.id = tr.run_id
            WHERE tr.status = 'complete'
              AND tr.stats IS NOT NULL
              {where_theme}
            ORDER BY tr.completed_at ASC
            {limit_clause}
        """)).mappings().all()

        print(f"Found {len(rows)} completed theme results to backfill.")
        if args.dry_run:
            print("[DRY RUN] No writes will be performed.")

        total_written = 0
        for row in rows:
            stats = dict(row["stats"] or {})
            stats["_primary_metric"] = row["metric_value"]
            observed_at = row["completed_at"]
            if observed_at and observed_at.tzinfo is None:
                from datetime import timezone
                observed_at = observed_at.replace(tzinfo=timezone.utc)

            if args.dry_run:
                scalar_count = sum(
                    1 for v in stats.values()
                    if isinstance(v, (int, float, bool))
                )
                print(f"  [{row['theme']}] aoi={row['aoi_id']} at {observed_at} -> {scalar_count} metrics")
                continue

            ts_session = get_sync_session()
            try:
                n = write_theme_metrics(
                    session=ts_session,
                    aoi_id=str(row["aoi_id"]),
                    theme=row["theme"],
                    observed_at=observed_at,
                    stats=stats,
                    confidence=row["confidence"],
                    data_source=row["data_source"],
                )
                total_written += n
            finally:
                ts_session.close()

        if not args.dry_run:
            print(f"Done. Wrote {total_written} total metric_timeseries rows.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
