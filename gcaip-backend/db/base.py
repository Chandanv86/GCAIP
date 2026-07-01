"""
SQLAlchemy declarative base.
Import all models here so Alembic autogenerate detects them.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def import_all_models():
    """Import all models so Alembic can see them for migrations.
    Call this from alembic/env.py — NOT at module level to avoid circular imports.
    """
    from models.user import User  # noqa: F401
    from models.aoi import AOI  # noqa: F401
    from models.analysis_run import AnalysisRun  # noqa: F401
    from models.theme_result import ThemeResult  # noqa: F401
    from models.risk_score import RiskScore  # noqa: F401
    from models.alert import Alert  # noqa: F401

