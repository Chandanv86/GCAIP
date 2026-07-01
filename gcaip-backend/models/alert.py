"""Alert records — triggered when risk thresholds are breached."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    aoi_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aois.id"), nullable=False
    )

    # Classification
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False  # INFO|WATCH|WARNING|EMERGENCY
    )
    theme: Mapped[str] = mapped_column(String(64), nullable=False)
    alert_type: Mapped[str] = mapped_column(
        String(64), nullable=False
        # flood_detected|spillway_risk|erosion_storm_risk|mangrove_loss|...
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Supporting data
    metric_value: Mapped[float | None] = mapped_column(Float)
    metric_unit: Mapped[str | None] = mapped_column(String(32))
    cross_insights: Mapped[list] = mapped_column(JSONB, default=list)
    tile_url: Mapped[str | None] = mapped_column(Text)

    # Lifecycle
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(32), default="active"  # active|resolved|false_positive
    )

    # Deduplication — prevents repeat alerts within same day for same condition
    dedup_key: Mapped[str | None] = mapped_column(String(512), unique=True)

    # Dispatch tracking
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    push_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationship
    aoi: Mapped["AOI"] = relationship("AOI", back_populates="alerts")

    __table_args__ = (
        Index("idx_alerts_aoi_time", "aoi_id", "triggered_at"),
        Index("idx_alerts_active", "status", "severity",
              postgresql_where="status = 'active'"),
    )
