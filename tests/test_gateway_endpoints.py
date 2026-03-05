"""
tests/test_gateway_endpoints.py

Full test suite for the POST /api/v1/gateway/packet endpoint.

Uses:
  - httpx.AsyncClient in ASGITransport mode (no real network)
  - SQLite in-memory engine (no PostgreSQL needed)
  - FastAPI test app wired to the gateway router

Tests cover:
  - Valid IMU packet POST → 202 Accepted, packet_type=1
  - Valid RTT packet POST → 202 Accepted, packet_type=2
  - Missing X-API-Key header → 401
  - Wrong X-API-Key value → 401
  - Malformed base64 payload → 400
  - Unknown packet type byte → 400 (ValueError from parser, not 500)
  - Malformed JSON body → 422 (Pydantic validation)
  - Invalid MAC format → 422
"""

from __future__ import annotations

import base64
import struct
from datetime import datetime, timezone
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
# Packet builders (mirror the test_ble_parser.py helpers)
# ─────────────────────────────────────────────────────────────────────────────

def _mac_bytes(mac_str: str = "24:42:E3:15:E5:72") -> bytes:
    return bytes(int(x, 16) for x in mac_str.split(":"))


def build_imu_bytes(
    mac: str = "24:42:E3:15:E5:72",
    ts_ms: int = 1000,
    ax: float = 0.1, ay: float = 0.2, az: float = 9.81,
    gx: float = 0.0, gy: float = 0.0, gz: float = 0.01,
    seq: int = 1,
) -> bytes:
    buf = bytearray(40)
    buf[0] = 0x01
    buf[1:7] = _mac_bytes(mac)
    struct.pack_into("<Q", buf, 7, ts_ms)
    struct.pack_into("<ffffff", buf, 15, ax, ay, az, gx, gy, gz)
    buf[39] = seq & 0xFF
    return bytes(buf)


def build_rtt_bytes(
    mac: str = "24:42:E3:15:E5:72",
    ts_ms: int = 2000,
    aps: list | None = None,
) -> bytes:
    aps = aps or []
    n = len(aps)
    buf = bytearray(16 + n * 16)
    buf[0] = 0x02
    buf[1:7] = _mac_bytes(mac)
    struct.pack_into("<Q", buf, 7, ts_ms)
    buf[15] = n
    for i, (bssid_str, d_mean, d_std, rssi, band) in enumerate(aps):
        off = 16 + i * 16
        buf[off:off+6] = _mac_bytes(bssid_str)
        struct.pack_into("<f", buf, off+6, d_mean)
        struct.pack_into("<f", buf, off+10, d_std)
        struct.pack_into("<b", buf, off+14, rssi)
        buf[off+15] = band
    return bytes(buf)


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def valid_body(payload_b64: str, mac: str = "24:42:E3:15:E5:72") -> dict:
    return {
        "device_mac": mac,
        "rx_ts_utc": "2026-03-05T00:00:00.000Z",
        "payload_b64": payload_b64,
    }


GOOD_HEADERS = {"X-API-Key": TEST_API_KEY}


# ─────────────────────────────────────────────────────────────────────────────
# Tests — valid packets
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_valid_imu_returns_202(client: AsyncClient):
    payload = b64(build_imu_bytes())
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=valid_body(payload),
        headers=GOOD_HEADERS,
    )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_valid_imu_response_body(client: AsyncClient):
    payload = b64(build_imu_bytes())
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=valid_body(payload),
        headers=GOOD_HEADERS,
    )
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["packet_type"] == 1
    assert data["device_mac"] == "24:42:E3:15:E5:72"


@pytest.mark.asyncio
async def test_valid_rtt_returns_202(client: AsyncClient):
    aps = [("AA:BB:CC:11:22:33", 5.0, 0.5, -65, 0x01)]
    payload = b64(build_rtt_bytes(aps=aps))
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=valid_body(payload),
        headers=GOOD_HEADERS,
    )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_valid_rtt_response_body(client: AsyncClient):
    aps = [("AA:BB:CC:11:22:33", 5.0, 0.5, -65, 0x01)]
    payload = b64(build_rtt_bytes(aps=aps))
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=valid_body(payload),
        headers=GOOD_HEADERS,
    )
    data = resp.json()
    assert data["packet_type"] == 2


@pytest.mark.asyncio
async def test_rtt_zero_aps_accepted(client: AsyncClient):
    """RTT packet with 0 AP records is valid (no APs in range)."""
    payload = b64(build_rtt_bytes(aps=[]))
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=valid_body(payload),
        headers=GOOD_HEADERS,
    )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_same_device_mac_reused(client: AsyncClient):
    """Two requests from the same MAC should not create duplicate Device rows."""
    payload = b64(build_imu_bytes())
    for _ in range(3):
        resp = await client.post(
            "/api/v1/gateway/packet",
            json=valid_body(payload),
            headers=GOOD_HEADERS,
        )
        assert resp.status_code == 202


# ─────────────────────────────────────────────────────────────────────────────
# Tests — authentication
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_api_key_returns_401(client: AsyncClient):
    payload = b64(build_imu_bytes())
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=valid_body(payload),
        # No X-API-Key header
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_wrong_api_key_returns_401(client: AsyncClient):
    payload = b64(build_imu_bytes())
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=valid_body(payload),
        headers={"X-API-Key": "completely-wrong-key"},
    )
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Tests — payload validation errors
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_malformed_base64_returns_400(client: AsyncClient):
    body = valid_body("!!!not-valid-base64!!!")
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=body,
        headers=GOOD_HEADERS,
    )
    assert resp.status_code == 400
    assert "base64" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unknown_type_byte_returns_400_not_500(client: AsyncClient):
    """Unknown type byte from the parser must produce 400, not 500."""
    bad_packet = bytes([0xAB]) + b"\x00" * 39
    payload = b64(bad_packet)
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=valid_body(payload),
        headers=GOOD_HEADERS,
    )
    assert resp.status_code == 400
    assert "parse error" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_truncated_imu_returns_400(client: AsyncClient):
    """Truncated IMU packet (too short) raises ValueError → 400."""
    short_packet = build_imu_bytes()[:20]
    payload = b64(short_packet)
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=valid_body(payload),
        headers=GOOD_HEADERS,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_empty_payload_returns_400(client: AsyncClient):
    """Empty base64 payload decodes to empty bytes → ValueError → 400."""
    payload = b64(b"")
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=valid_body(payload),
        headers=GOOD_HEADERS,
    )
    assert resp.status_code == 400


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
async def test_invalid_mac_format_returns_422(client: AsyncClient):
    payload = b64(build_imu_bytes())
    body = {
        "device_mac": "ZZZZ",
        "rx_ts_utc": "2026-03-05T00:00:00Z",
        "payload_b64": payload,
    }
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=body,
        headers=GOOD_HEADERS,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_missing_payload_b64_field_returns_422(client: AsyncClient):
    body = {
        "device_mac": "24:42:E3:15:E5:72",
        "rx_ts_utc": "2026-03-05T00:00:00Z",
        # payload_b64 missing
    }
    resp = await client.post(
        "/api/v1/gateway/packet",
        json=body,
        headers=GOOD_HEADERS,
    )
    assert resp.status_code == 422
