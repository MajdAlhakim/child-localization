"""
backend/app/models.py

SQLAlchemy ORM models.

Hierarchy:
  Venue  1──* FloorPlan  1──* AccessPoint
                         1──* GridPoint
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, ForeignKey, Integer, Text, UniqueConstraint, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Uuid


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Venue(Base):
    __tablename__ = "venues"

    id:          Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name:        Mapped[str]       = mapped_column(String(255))
    description: Mapped[str]       = mapped_column(Text, default="")
    created_at:  Mapped[datetime]  = mapped_column(DateTime, default=_now)

    floor_plans: Mapped[list["FloorPlan"]] = relationship(
        back_populates="venue",
        cascade="all, delete-orphan",
        order_by="FloorPlan.floor_number",
    )


class FloorPlan(Base):
    __tablename__ = "floor_plans"

    id:             Mapped[uuid.UUID]      = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    venue_id:       Mapped[uuid.UUID]      = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"))
    name:           Mapped[str]            = mapped_column(String(255), default="Floor 1")
    floor_number:   Mapped[int]            = mapped_column(Integer, default=1)
    scale_px_per_m: Mapped[float]          = mapped_column(Float, default=10.0)
    grid_spacing_m: Mapped[float]          = mapped_column(Float, default=0.5)
    image_path:     Mapped[str | None]     = mapped_column(Text, nullable=True)
    created_at:     Mapped[datetime]       = mapped_column(DateTime, default=_now)

    venue:         Mapped["Venue"]               = relationship(back_populates="floor_plans")
    access_points: Mapped[list["AccessPoint"]]   = relationship(
        back_populates="floor_plan", cascade="all, delete-orphan"
    )
    grid_points:   Mapped[list["GridPoint"]]     = relationship(
        back_populates="floor_plan", cascade="all, delete-orphan"
    )


class AccessPoint(Base):
    """
    One row per BSSID per floor plan.

    group_id links multiple BSSIDs that belong to the same physical AP
    (same MAC prefix, different last octet — enterprise AP subnet broadcasting).
    All BSSIDs in a group share the same (x, y) position.
    """
    __tablename__  = "access_points"
    __table_args__ = (UniqueConstraint("floor_plan_id", "bssid"),)

    id:             Mapped[uuid.UUID]       = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    floor_plan_id:  Mapped[uuid.UUID]       = mapped_column(ForeignKey("floor_plans.id", ondelete="CASCADE"))
    group_id:       Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    bssid:          Mapped[str]             = mapped_column(String(17))
    ssid:           Mapped[str]             = mapped_column(String(255), default="")
    rssi_ref:       Mapped[float]           = mapped_column(Float, default=-40.0)
    path_loss_n:    Mapped[float]           = mapped_column(Float, default=2.7)
    x:              Mapped[float]           = mapped_column(Float, default=0.0)
    y:              Mapped[float]           = mapped_column(Float, default=0.0)
    ceiling_height: Mapped[float]           = mapped_column(Float, default=3.0)

    floor_plan: Mapped["FloorPlan"] = relationship(back_populates="access_points")


class GridPoint(Base):
    __tablename__ = "grid_points"

    id:            Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    floor_plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("floor_plans.id", ondelete="CASCADE"))
    x:             Mapped[float]     = mapped_column(Float)
    y:             Mapped[float]     = mapped_column(Float)

    floor_plan: Mapped["FloorPlan"] = relationship(back_populates="grid_points")
