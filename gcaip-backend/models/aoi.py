"""
AOI (Area of Interest) ORM model.
Stores the user-drawn polygon + admin metadata derived from reverse geocoding.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry

from db.base import Base


class AOI(Base):
    __tablename__ = "aois"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str | None] = mapped_column(String(512))

    # Geometry stored as WGS84 (SRID 4326)
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326), nullable=False
    )
    bbox: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326)
    )
    area_km2: Mapped[float | None] = mapped_column(Float)

    # Admin metadata from reverse geocode
    country_code: Mapped[str | None] = mapped_column(String(2))
    admin_level1: Mapped[str | None] = mapped_column(String(256))  # Province/State
    admin_level2: Mapped[str | None] = mapped_column(String(256))  # District

    # Access control
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    creator: Mapped["User | None"] = relationship("User", back_populates="aois")
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(
        "AnalysisRun", back_populates="aoi"
    )
    alerts: Mapped[list["Alert"]] = relationship("Alert", back_populates="aoi")

    __table_args__ = (
        Index("idx_aois_geom", "geom", postgresql_using="gist"),
        Index("idx_aois_user", "created_by"),
    )
