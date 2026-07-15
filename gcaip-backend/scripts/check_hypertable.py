import sys
sys.path.insert(0, ".")

from db.utils import get_sync_session
from sqlalchemy import text

session = get_sync_session()
try:
    # 1. Table existence
    r1 = session.execute(text("SELECT to_regclass('public.metric_timeseries')")).scalar()
    print("metric_timeseries table:", r1 if r1 else "MISSING")

    # 2. Hypertable confirmation
    q2 = "SELECT count(*) FROM timescaledb_information.hypertables WHERE hypertable_name = 'metric_timeseries'"
    r2 = session.execute(text(q2)).scalar()
    print("Is TimescaleDB hypertable (1=yes, 0=no):", r2)

    # 3. Continuous aggregate
    r3 = session.execute(text("SELECT to_regclass('public.metric_daily')")).scalar()
    print("metric_daily view:", r3 if r3 else "MISSING")

    # 4. Row count
    r4 = session.execute(text("SELECT count(*) FROM metric_timeseries")).scalar()
    print("Rows currently in metric_timeseries:", r4)

    # 5. Alembic versions
    r5 = session.execute(text("SELECT version_num FROM alembic_version")).fetchall()
    print("Applied alembic migrations:", [row[0] for row in r5])

finally:
    session.close()
