-- GCAIP — Database bootstrap script
-- Runs automatically on first container start via docker-entrypoint-initdb.d
-- Alembic migrations (001_initial.py) handle table creation; this just
-- ensures extensions are available before Alembic runs.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Performance: increase statistics target for geometry columns
ALTER DATABASE gcaip SET random_page_cost = 1.1;
