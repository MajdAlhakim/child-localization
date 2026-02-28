"""Tests for TASK-03: PostgreSQL schema and SQLAlchemy models.

Uses SQLite in-memory (aiosqlite) — no live database required.
"""
import pytest
import pytest_asyncio
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

from backend.app.db.models import (
    Base, Device, DeviceLink, ParentUser, AccessPoint,
    ApCalibration, ImuSample, RttMeasurement, PositionEstimate,
)
from backend.app.db.init_db import init_db, drop_db

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine() -> AsyncEngine:
    eng = create_async_engine(TEST_DB_URL, future=True)
    await init_db(bind=eng)
    yield eng
    await drop_db(bind=eng)
    await eng.dispose()


# ── Table existence ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_tables_created(engine: AsyncEngine):
    async with engine.connect() as conn:
        table_names = await conn.run_sync(
            lambda c: inspect(c).get_table_names()
        )
    expected = {
        "devices", "device_links", "parent_users", "access_points",
        "ap_calibration", "imu_samples", "rtt_measurements", "position_estimates",
    }
    assert expected.issubset(set(table_names)), (
        f"Missing tables: {expected - set(table_names)}"
    )


# ── Column presence ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_devices_columns(engine: AsyncEngine):
    async with engine.connect() as conn:
        cols = {c["name"] for c in await conn.run_sync(
            lambda c: inspect(c).get_columns("devices")
        )}
    for col in ("device_id", "mac_address", "label", "created_at", "updated_at", "is_active"):
        assert col in cols, f"Missing column: {col}"


@pytest.mark.asyncio
async def test_device_links_columns(engine: AsyncEngine):
    async with engine.connect() as conn:
        cols = {c["name"] for c in await conn.run_sync(
            lambda c: inspect(c).get_columns("device_links")
        )}
    for col in ("link_id", "device_id", "parent_user_id", "linked_at"):
        assert col in cols, f"Missing column: {col}"


@pytest.mark.asyncio
async def test_access_points_columns(engine: AsyncEngine):
    async with engine.connect() as conn:
        cols = {c["name"] for c in await conn.run_sync(
            lambda c: inspect(c).get_columns("access_points")
        )}
    for col in ("ap_id", "bssid", "ssid", "x_m", "y_m", "z_m", "band", "created_at"):
        assert col in cols, f"Missing column: {col}"


@pytest.mark.asyncio
async def test_ap_calibration_columns(engine: AsyncEngine):
    async with engine.connect() as conn:
        cols = {c["name"] for c in await conn.run_sync(
            lambda c: inspect(c).get_columns("ap_calibration")
        )}
    for col in ("cal_id", "ap_id", "band", "offset_m", "std_dev_m",
                "sample_count", "calibrated_at", "is_reliable"):
        assert col in cols, f"Missing column: {col}"


@pytest.mark.asyncio
async def test_imu_samples_columns(engine: AsyncEngine):
    async with engine.connect() as conn:
        cols = {c["name"] for c in await conn.run_sync(
            lambda c: inspect(c).get_columns("imu_samples")
        )}
    for col in ("sample_id", "device_id", "ts_device_ms", "ts_server",
                "ax_ms2", "ay_ms2", "az_ms2", "gx_rads", "gy_rads", "gz_rads", "seq"):
        assert col in cols, f"Missing column: {col}"


@pytest.mark.asyncio
async def test_rtt_measurements_columns(engine: AsyncEngine):
    async with engine.connect() as conn:
        cols = {c["name"] for c in await conn.run_sync(
            lambda c: inspect(c).get_columns("rtt_measurements")
        )}
    for col in ("meas_id", "device_id", "ap_id", "ts_device_ms", "ts_server",
                "d_raw_mean_m", "d_raw_std_m", "d_corrected_m", "rssi_dbm", "band"):
        assert col in cols, f"Missing column: {col}"


@pytest.mark.asyncio
async def test_position_estimates_columns(engine: AsyncEngine):
    async with engine.connect() as conn:
        cols = {c["name"] for c in await conn.run_sync(
            lambda c: inspect(c).get_columns("position_estimates")
        )}
    for col in ("pos_id", "device_id", "ts_server", "x_m", "y_m",
                "source", "confidence", "active_aps", "mode"):
        assert col in cols, f"Missing column: {col}"


# ── ORM relationship existence ────────────────────────────────────────────────

def test_device_relationships():
    mapper = inspect(Device)
    rel_names = {r.key for r in mapper.relationships}
    assert "links" in rel_names
    assert "imu_samples" in rel_names
    assert "rtt_measurements" in rel_names
    assert "position_estimates" in rel_names


def test_device_link_relationships():
    mapper = inspect(DeviceLink)
    rel_names = {r.key for r in mapper.relationships}
    assert "device" in rel_names
    assert "parent_user" in rel_names


def test_ap_calibration_relationship():
    mapper = inspect(ApCalibration)
    rel_names = {r.key for r in mapper.relationships}
    assert "access_point" in rel_names


# ── Default values ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_device_is_active_default_true(engine: AsyncEngine):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        dev = Device(mac_address="AA:BB:CC:DD:EE:FF")
        session.add(dev)
        await session.commit()
        await session.refresh(dev)
        assert dev.is_active is True


@pytest.mark.asyncio
async def test_ap_calibration_is_reliable_default_true(engine: AsyncEngine):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        ap = AccessPoint(bssid="AA:BB:CC:DD:EE:01")
        session.add(ap)
        await session.flush()
        cal = ApCalibration(
            ap_id=ap.ap_id, band="5GHz",
            offset_m=2500.0, std_dev_m=5.0, sample_count=100,
        )
        session.add(cal)
        await session.commit()
        await session.refresh(cal)
        assert cal.is_reliable is True
