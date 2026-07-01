"""Analysis run — tracks a full 7-theme Celery job lifecycle."""
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    aoi_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aois.id"), nullable=False, index=True
    )

    # Job state
    status: Mapped[str] = mapped_column(
        String(32), default="pending"  # pending|running|complete|failed
    )
    triggered_by: Mapped[str] = mapped_column(
        String(32), default="user"  # user|schedule|alert
    )

    # Analysis window
    date_range_start: Mapped[date] = mapped_column(Date, nullable=False)
    date_range_end: Mapped[date] = mapped_column(Date, nullable=False)

    # Celery orchestration
    celery_task_id: Mapped[str | None] = mapped_column(String(255))

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_sec: Mapped[float | None] = mapped_column(Float)

    # Error handling
    error_message: Mapped[str | None] = mapped_column(Text)

    # GEE quota accounting
    gee_quota_used: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    aoi: Mapped["AOI"] = relationship("AOI", back_populates="analysis_runs")
    theme_results: Mapped[list["ThemeResult"]] = relationship(
        "ThemeResult", back_populates="run"
    )
    risk_score: Mapped["RiskScore | None"] = relationship(
        "RiskScore", back_populates="run", uselist=False
    )

    __table_args__ = (
        Index("idx_runs_aoi_time", "aoi_id", "created_at"),
        Index("idx_runs_status", "status"),
    )
