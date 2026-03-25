"""SQLAlchemy 2.0 ORM models — PRD Section 13."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, Float, ForeignKey, Integer, SmallInteger,
    String, BigInteger, text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy import DateTime


def _uuid_col(primary_key: bool = False) -> Column:
    """UUID column that works with both PostgreSQL and SQLite (for tests)."""
    return Column(
        PG_UUID(as_uuid=True),
        primary_key=primary_key,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()") if not primary_key else None,
        nullable=False,
    )


def _now_col() -> Column:
    return Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class Base(DeclarativeBase):
    pass


class Device(Base):
    __tablename__ = "devices"

    device_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mac_address = Column(String(17), unique=True, nullable=False)
    label = Column(String(100), nullable=True)
    created_at = _now_col()
    updated_at = _now_col()
    is_active = Column(Boolean, nullable=False, default=True)

    links = relationship("DeviceLink", back_populates="device", cascade="all, delete")
    imu_samples = relationship("ImuSample", back_populates="device", cascade="all, delete")
    rtt_measurements = relationship("RttMeasurement", back_populates="device", cascade="all, delete")
    position_estimates = relationship("PositionEstimate", back_populates="device", cascade="all, delete")


class ParentUser(Base):
    """Parent user table — implemented by person-d (TASK-15), defined here for FK."""
    __tablename__ = "parent_users"

    user_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = _now_col()

    links = relationship("DeviceLink", back_populates="parent_user", cascade="all, delete")


class DeviceLink(Base):
    __tablename__ = "device_links"

    link_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("devices.device_id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("parent_users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    linked_at = _now_col()

    device = relationship("Device", back_populates="links")
    parent_user = relationship("ParentUser", back_populates="links")


class AccessPoint(Base):
    __tablename__ = "access_points"

    ap_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bssid = Column(String(17), unique=True, nullable=False)
    ssid = Column(String(100), nullable=True)
    x_m = Column(Float, nullable=True)   # OQ-03: pending IT confirmation
    y_m = Column(Float, nullable=True)
    z_m = Column(Float, nullable=True)
    band = Column(String(10), nullable=True)  # "2.4GHz" or "5GHz"
    created_at = _now_col()

    calibration_entries = relationship("ApCalibration", back_populates="access_point", cascade="all, delete")
    rtt_measurements = relationship("RttMeasurement", back_populates="access_point", cascade="all, delete")


class ApCalibration(Base):
    __tablename__ = "ap_calibration"

    cal_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ap_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("access_points.ap_id", ondelete="CASCADE"),
        nullable=False,
    )
    band = Column(String(10), nullable=False)
    offset_m = Column(Float, nullable=False)
    std_dev_m = Column(Float, nullable=False)
    sample_count = Column(Integer, nullable=False)
    calibrated_at = _now_col()
    is_reliable = Column(Boolean, nullable=False, default=True)

    access_point = relationship("AccessPoint", back_populates="calibration_entries")


class ImuSample(Base):
    __tablename__ = "imu_samples"

    sample_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("devices.device_id", ondelete="CASCADE"),
        nullable=False,
    )
    ts_device_ms = Column(BigInteger, nullable=False)
    ts_server = _now_col()
    ax_ms2 = Column(Float, nullable=False)
    ay_ms2 = Column(Float, nullable=False)
    az_ms2 = Column(Float, nullable=False)
    gx_rads = Column(Float, nullable=False)
    gy_rads = Column(Float, nullable=False)
    gz_rads = Column(Float, nullable=False)
    seq = Column(SmallInteger, nullable=True)   # nullable: ESP32-C5 firmware does not send seq

    device = relationship("Device", back_populates="imu_samples")


class RttMeasurement(Base):
    __tablename__ = "rtt_measurements"

    meas_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("devices.device_id", ondelete="CASCADE"),
        nullable=False,
    )
    ap_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("access_points.ap_id", ondelete="CASCADE"),
        nullable=False,
    )
    ts_device_ms = Column(BigInteger, nullable=False)
    ts_server = _now_col()
    d_raw_mean_m = Column(Float, nullable=True)   # nullable: NULL when only RSSI is available (ESP32-C5)
    d_raw_std_m = Column(Float, nullable=True)    # nullable: NULL when only RSSI is available (ESP32-C5)
    d_corrected_m = Column(Float, nullable=True)
    rssi_dbm = Column(SmallInteger, nullable=False)
    band = Column(String(10), nullable=False)

    device = relationship("Device", back_populates="rtt_measurements")
    access_point = relationship("AccessPoint", back_populates="rtt_measurements")


class PositionEstimate(Base):
    __tablename__ = "position_estimates"

    pos_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("devices.device_id", ondelete="CASCADE"),
        nullable=False,
    )
    ts_server = _now_col()
    x_m = Column(Float, nullable=False)
    y_m = Column(Float, nullable=False)
    source = Column(String(20), nullable=False)   # "fused"|"wifi_only"|"imu_only"
    confidence = Column(Float, nullable=False)
    active_aps = Column(SmallInteger, nullable=False)
    mode = Column(String(20), nullable=False)

    device = relationship("Device", back_populates="position_estimates")
