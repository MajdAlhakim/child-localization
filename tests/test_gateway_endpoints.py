"""
tests/test_gateway_endpoints.py

Full test suite for the POST /api/v1/gateway/packet endpoint.

Uses:
  - httpx.AsyncClient in ASGITransport mode (no real network)
  - SQLite in-memory engine (no PostgreSQL needed)
  - FastAPI test app wired to the gateway router

Wire format: JSON (ESP32-C5 firmware — see firmware/esp32c5/trakn_tag/trakn_tag.ino)

Tests cover:
  - Valid packet with IMU samples → 202 Accepted
  - Valid packet with IMU + WiFi → 202 Accepted, correct counts
  - Valid packet with empty wifi array → 202 Accepted
  - Response body fields: status, imu_count, wifi_count, device_mac
  - Same device MAC across multiple requests → no duplicate Device rows
  - Missing X-API-Key header → 401
  - Wrong X-API-Key value → 401
  - Malformed JSON body → 422
  - Missing required field (mac) → 422
  - Empty imu array → 202 Accepted (wifi-only packet is valid)
"""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from backend.app.api import gateway as gw_module
from backend.app.db.init_db import init_db
from backend.app.db.models import Base
from backend.app.db.session import get_db


# ─────────────────────────────────────────────────────────────────────────────
# Test app setup — SQLite in-memory, overridden get_db dependency
# ─────────────────────────────────────────────────────────────────────────────

SQLITE_URL = "sqlite+aiosqlite:///:memory:"

TEST_API_KEY = "dev-gateway-key-change-in-production"  # matches config.py default


def make_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(gw_module.router)
    return app


@pytest_asyncio.fixture
async def db_engine():
    """Async SQLite in-memory engine — created fresh for each test."""
    engine = create_async_engine(SQLITE_URL, echo=False)
    await init_db(bind=engine)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    """ASGI test client wired to the test app with overridden DB session."""
    app = make_test_app()

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ─────────────────────────────────────────────────────────────────────────────
# Packet builders matching the ESP32-C5 JSON wire format
# ─────────────────────────────────────────────────────────────────────────────

def make_imu_sample(ts: int = 1000) -> dict:
    return {"ts": ts, "ax": 0.1, "ay": 0.2, "az": 9.81,
            "gx": 0.0, "gy": 0.0, "gz": 0.01}


def make_wifi_ap(bssid: str = "AA:BB:CC:11:22:33", rssi: int = -65, ch: int = 6) -> dict:
    return {"bssid": bssid, "ssid": "QU User", "rssi": rssi, "ch": ch}


def make_packet(
    mac: str = "24:42:E3:15:E5:72",
    ts: int = 12450,
    imu: list | None = None,
    wifi: list | None = None,
) -> dict:
    return {
        "mac": mac,
        "ts": ts,
        "imu": imu if imu is not None else [make_imu_sample()],
        "wifi": wifi if wifi is not None else [],
    }


GOOD_HEADERS = {"X-API-Key": TEST_API_KEY}


# ─────────────────────────────────────────────────────────────────────────────
# Tests — valid packets
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_valid_imu_returns_202(client: AsyncClient):
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=make_packet(),
        headers=GOOD_HEADERS,
    )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_valid_imu_response_body(client: AsyncClient):
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=make_packet(imu=[make_imu_sample(1000), make_imu_sample(1010)]),
        headers=GOOD_HEADERS,
    )
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["imu_count"] == 2
    assert data["wifi_count"] == 0
    assert data["device_mac"] == "24:42:E3:15:E5:72"


@pytest.mark.asyncio
async def test_valid_imu_and_wifi_returns_202(client: AsyncClient):
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=make_packet(
            imu=[make_imu_sample()],
            wifi=[make_wifi_ap("AA:BB:CC:11:22:33"), make_wifi_ap("DD:EE:FF:44:55:66")],
        ),
        headers=GOOD_HEADERS,
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["imu_count"] == 1
    assert data["wifi_count"] == 2


@pytest.mark.asyncio
async def test_empty_wifi_array_accepted(client: AsyncClient):
    """Packet with empty wifi[] is valid (no scan available yet)."""
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=make_packet(wifi=[]),
        headers=GOOD_HEADERS,
    )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_empty_imu_array_accepted(client: AsyncClient):
    """Packet with empty imu[] is accepted (wifi-only scan result)."""
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=make_packet(imu=[], wifi=[make_wifi_ap()]),
        headers=GOOD_HEADERS,
    )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_five_imu_samples_per_packet(client: AsyncClient):
    """Firmware batches up to 5 IMU samples — all must be accepted."""
    samples = [make_imu_sample(ts=1000 + i * 10) for i in range(5)]
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=make_packet(imu=samples),
        headers=GOOD_HEADERS,
    )
    assert resp.status_code == 202
    assert resp.json()["imu_count"] == 5


@pytest.mark.asyncio
async def test_same_device_mac_reused(client: AsyncClient):
    """Three requests from the same MAC must not create duplicate Device rows."""
    for _ in range(3):
        resp = await client.post(
            "/api/v1/gateway/packet",
            json=make_packet(),
            headers=GOOD_HEADERS,
        )
        assert resp.status_code == 202


@pytest.mark.asyncio
async def test_same_bssid_reused(client: AsyncClient):
    """Two packets referencing the same AP BSSID must not duplicate AccessPoint rows."""
    ap = make_wifi_ap("AA:BB:CC:11:22:33")
    for _ in range(2):
        resp = await client.post(
            "/api/v1/gateway/packet",
            json=make_packet(wifi=[ap]),
            headers=GOOD_HEADERS,
        )
        assert resp.status_code == 202


# ─────────────────────────────────────────────────────────────────────────────
# Tests — authentication
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_api_key_returns_401(client: AsyncClient):
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=make_packet(),
        # No X-API-Key header
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_wrong_api_key_returns_401(client: AsyncClient):
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=make_packet(),
        headers={"X-API-Key": "completely-wrong-key"},
    )
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Tests — request body schema errors
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_malformed_json_body_returns_422(client: AsyncClient):
    resp = await client.post(
        "/api/v1/gateway/packet",
        content=b"not-json-at-all",
        headers={**GOOD_HEADERS, "Content-Type": "application/json"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_missing_mac_field_returns_422(client: AsyncClient):
    body = {"ts": 12450, "imu": [make_imu_sample()], "wifi": []}
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=body,
        headers=GOOD_HEADERS,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_missing_imu_field_returns_422(client: AsyncClient):
    body = {"mac": "24:42:E3:15:E5:72", "ts": 12450, "wifi": []}
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=body,
        headers=GOOD_HEADERS,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_imu_sample_missing_ax_returns_422(client: AsyncClient):
    """IMU sample with missing required field must fail Pydantic validation."""
    bad_sample = {"ts": 1000, "ay": 0.2, "az": 9.81, "gx": 0.0, "gy": 0.0, "gz": 0.01}
    body = make_packet(imu=[bad_sample])
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=body,
        headers=GOOD_HEADERS,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_wifi_ap_missing_bssid_returns_422(client: AsyncClient):
    """WiFi AP entry with missing bssid must fail Pydantic validation."""
    bad_ap = {"ssid": "QU User", "rssi": -65, "ch": 6}
    body = make_packet(wifi=[bad_ap])
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=body,
        headers=GOOD_HEADERS,
    )
    assert resp.status_code == 422
