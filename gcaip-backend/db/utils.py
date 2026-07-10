"""
db/utils.py — shared database helpers for Celery task modules.

Centralises the asyncpg→psycopg2 driver replacement so any future change to
DATABASE_URL format only needs updating here, and a clear error is raised if
the substitution fails to match rather than silently propagating a broken URL.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import settings


def make_sync_db_url() -> str:
    """
    Convert the async DATABASE_URL (postgresql+asyncpg://…) to a synchronous
    psycopg2 URL for use in Celery workers.

    Raises:
        RuntimeError: if the URL doesn't contain the expected asyncpg scheme,
                      so the caller gets a clear error instead of a downstream
                      SQLAlchemy dialect error.
    """
    url = settings.DATABASE_URL
    if "postgresql+asyncpg://" not in url:
        raise RuntimeError(
            f"DATABASE_URL does not use the expected 'postgresql+asyncpg://' scheme. "
            f"Got: '{url[:60]}…'. Update db/utils.py:make_sync_db_url() if the scheme changed."
        )
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


def get_sync_session() -> Session:
    """
    Create and return a synchronous SQLAlchemy session for use in Celery tasks.
    Callers are responsible for calling session.close() in a finally block.
    """
    engine = create_engine(make_sync_db_url(), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
