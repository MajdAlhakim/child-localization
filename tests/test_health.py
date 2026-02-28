"""Tests for TASK-19: health check endpoint.

PRD §14.4 expected response:
    { "status": "healthy", "database": "connected",
      "fusion_engine": "running", "active_devices": int, "uptime_seconds": int }
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from backend.app.db.init_db import init_db, drop_db
from backend.app.db.session import get_db
from backend.app.main import app

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


@pytest.mark.asyncio
async def test_health_returns_200(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_schema(client):
    resp = await client.get("/api/v1/health")
    data = resp.json()
    assert "status" in data
    assert "database" in data
    assert "fusion_engine" in data
    assert "active_devices" in data
    assert "uptime_seconds" in data


@pytest.mark.asyncio
async def test_health_status_healthy(client):
    resp = await client.get("/api/v1/health")
    assert resp.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_database_connected(client):
    resp = await client.get("/api/v1/health")
    assert resp.json()["database"] == "connected"


@pytest.mark.asyncio
async def test_health_active_devices_is_int(client):
    resp = await client.get("/api/v1/health")
    assert isinstance(resp.json()["active_devices"], int)


@pytest.mark.asyncio
async def test_health_uptime_is_non_negative(client):
    resp = await client.get("/api/v1/health")
    assert resp.json()["uptime_seconds"] >= 0
