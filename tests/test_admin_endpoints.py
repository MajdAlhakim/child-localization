"""Tests for TASK-08: calibration admin endpoints.

Uses SQLite in-memory + AsyncClient against the real FastAPI app.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from backend.app.db.init_db import init_db, drop_db
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.core.security import create_access_token

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def test_engine():
    eng = create_async_engine(TEST_DB_URL, future=True)
    await init_db(bind=eng)
    yield eng
    await drop_db(bind=eng)
    await eng.dispose()


@pytest_asyncio.fixture
async def client(test_engine):
    Session = async_sessionmaker(test_engine, expire_on_commit=False)

    async def override_get_db():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


def _auth_headers() -> dict:
    token = create_access_token({"sub": "test-admin"})
    return {"Authorization": f"Bearer {token}"}


_SAMPLE_PAYLOAD = {
    "bssid": "AA:BB:CC:DD:EE:01",
    "band": "5GHz",
    "offset_m": 2587.3,
    "std_dev_m": 5.0,
    "sample_count": 100,
}


@pytest.mark.asyncio
async def test_create_calibration_entry(client):
    resp = await client.post("/api/v1/admin/calibration", json=_SAMPLE_PAYLOAD, headers=_auth_headers())
    assert resp.status_code == 201
    data = resp.json()
    assert data["bssid"] == "AA:BB:CC:DD:EE:01"
    assert data["offset_m"] == pytest.approx(2587.3)
    assert data["is_reliable"] is True


@pytest.mark.asyncio
async def test_get_all_calibration(client):
    await client.post("/api/v1/admin/calibration", json=_SAMPLE_PAYLOAD, headers=_auth_headers())
    resp = await client.get("/api/v1/admin/calibration", headers=_auth_headers())
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_get_calibration_by_bssid(client):
    await client.post("/api/v1/admin/calibration", json=_SAMPLE_PAYLOAD, headers=_auth_headers())
    resp = await client.get("/api/v1/admin/calibration/AA:BB:CC:DD:EE:01", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()["bssid"] == "AA:BB:CC:DD:EE:01"


@pytest.mark.asyncio
async def test_get_calibration_by_bssid_not_found(client):
    resp = await client.get("/api/v1/admin/calibration/FF:FF:FF:FF:FF:FF", headers=_auth_headers())
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_calibration(client):
    await client.post("/api/v1/admin/calibration", json=_SAMPLE_PAYLOAD, headers=_auth_headers())
    resp = await client.delete("/api/v1/admin/calibration/AA:BB:CC:DD:EE:01", headers=_auth_headers())
    assert resp.status_code == 204
    # Confirm deleted
    resp2 = await client.get("/api/v1/admin/calibration/AA:BB:CC:DD:EE:01", headers=_auth_headers())
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_calibration_unreliable_flag_high_std(client):
    payload = {**_SAMPLE_PAYLOAD, "std_dev_m": 25.0, "bssid": "AA:BB:CC:DD:EE:02"}
    resp = await client.post("/api/v1/admin/calibration", json=payload, headers=_auth_headers())
    assert resp.status_code == 201
    assert resp.json()["is_reliable"] is False


@pytest.mark.asyncio
async def test_calibration_unreliable_flag_low_count(client):
    payload = {**_SAMPLE_PAYLOAD, "sample_count": 15, "bssid": "AA:BB:CC:DD:EE:03"}
    resp = await client.post("/api/v1/admin/calibration", json=payload, headers=_auth_headers())
    assert resp.status_code == 201
    assert resp.json()["is_reliable"] is False


@pytest.mark.asyncio
async def test_auth_required_no_token(client):
    resp = await client.get("/api/v1/admin/calibration")
    assert resp.status_code in (401, 403)
