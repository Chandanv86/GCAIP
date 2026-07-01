"""Per-theme GEE output — tile URL, stats, enrichment, quality indicators."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class ThemeResult(Base):
    __tablename__ = "theme_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_runs.id"), nullable=False, index=True
    )
    theme: Mapped[str] = mapped_column(
        String(64), nullable=False
        # flood|rainfall|reservoir|mangrove|erosion|vegetation|landuse
    )
    status: Mapped[str] = mapped_column(
        String(32), default="pending"  # pending|running|complete|failed|skipped
    )

    # GEE tile URL (expires ~6h from generation)
    tile_url: Mapped[str | None] = mapped_column(Text)
    tile_url_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vis_params: Mapped[dict | None] = mapped_column(JSONB)

    # Primary metric
    metric_value: Mapped[float | None] = mapped_column(Float)
    metric_unit: Mapped[str | None] = mapped_column(String(32))
    metric_label: Mapped[str | None] = mapped_column(String(512))

    # Raw GEE statistics
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Enriched context (population, OSM assets, trajectories)
    enrichment: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Quality indicators
    anomaly_score: Mapped[float | None] = mapped_column(Float)  # 0–100
    confidence: Mapped[float | None] = mapped_column(Float)     # 0–1
    data_age_hours: Mapped[float | None] = mapped_column(Float)
    data_source: Mapped[str | None] = mapped_column(String(512))

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    # Relationship
    run: Mapped["AnalysisRun"] = relationship("AnalysisRun", back_populates="theme_results")

    __table_args__ = (
        UniqueConstraint("run_id", "theme", name="uq_run_theme"),
        Index("idx_results_run", "run_id"),
        Index("idx_results_theme_time", "theme", "completed_at"),
    )
