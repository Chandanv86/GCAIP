import sys
sys.path.insert(0, ".")

from db.utils import get_sync_session
from sqlalchemy import text
from services.timeseries_writer import get_yearly_trend, get_available_metric_names

session = get_sync_session()
try:
    # Final row count
    count = session.execute(text("SELECT count(*) FROM metric_timeseries")).scalar()
    print(f"Total rows in metric_timeseries: {count}")

    # Distinct AOIs and themes
    combos = session.execute(text(
        "SELECT DISTINCT aoi_id, theme FROM metric_timeseries ORDER BY theme"
    )).fetchall()
    print(f"\nDistinct (aoi_id, theme) pairs: {len(combos)}")
    for row in combos[:5]:
        print(f"  aoi={row[0]}  theme={row[1]}")
    if len(combos) > 5:
        print(f"  ... and {len(combos)-5} more")

    # Sample: get yearly trend for first rainfall AOI
    rainfall_aois = [r[0] for r in combos if r[1] == "rainfall"]
    if rainfall_aois:
        sample_aoi = str(rainfall_aois[0])
        metrics = get_available_metric_names(session, sample_aoi, "rainfall")
        print(f"\nAvailable rainfall metrics for AOI {sample_aoi[:8]}...: {metrics}")

        if "spi_7" in metrics:
            trend = get_yearly_trend(session, sample_aoi, "rainfall", "spi_7", years_back=5)
            print(f"Yearly spi_7 trend ({len(trend)} year buckets): {trend}")

    # Test metric_daily view
    daily = session.execute(text(
        "SELECT count(*) FROM metric_daily"
    )).scalar()
    print(f"\nRows in metric_daily (continuous aggregate): {daily}")

finally:
    session.close()
