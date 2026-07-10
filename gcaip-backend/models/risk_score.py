"""Composite risk score — aggregates all 7 themes into a single decision score."""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class RiskScore(Base):
    __tablename__ = "risk_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_runs.id"), nullable=False, unique=True
    )
    aoi_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aois.id"), nullable=False
    )

    # Composite score — what users see first
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    overall_label: Mapped[str] = mapped_column(
        String(16), nullable=False  # LOW|MODERATE|HIGH|CRITICAL
    )

    # Component scores (all 0–100)
    flood_risk: Mapped[float | None] = mapped_column(Float)          # 35% weight
    erosion_risk: Mapped[float | None] = mapped_column(Float)        # 20% weight
    water_stress: Mapped[float | None] = mapped_column(Float)        # 15% weight
    vegetation_health: Mapped[float | None] = mapped_column(Float)   # 15% weight
    landuse_pressure: Mapped[float | None] = mapped_column(Float)    # 15% weight
    water_sanitation_pressure: Mapped[float | None] = mapped_column(Float)
    infrastructure_integrity: Mapped[float | None] = mapped_column(Float)

    # Cross-theme compound insights
    cross_insights: Mapped[list] = mapped_column(JSONB, default=list)

    # Population exposure
    population_in_aoi: Mapped[int | None] = mapped_column(BigInteger)
    population_at_risk: Mapped[int | None] = mapped_column(BigInteger)

    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    run: Mapped["AnalysisRun"] = relationship("AnalysisRun", back_populates="risk_score")

    __table_args__ = (
        Index("idx_risk_aoi_time", "aoi_id", "scored_at"),
    )
