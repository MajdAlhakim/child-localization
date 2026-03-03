"""Parent-facing REST endpoints and health check.

PRD §14.3:
    POST   /api/v1/auth/login
    GET    /api/v1/devices
    GET    /api/v1/devices/{id}/position
    GET    /api/v1/health
"""
import time
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.security import create_access_token, verify_password, verify_token, get_password_hash
from backend.app.db.models import Device, ParentUser, PositionEstimate
from backend.app.db.session import get_db

router = APIRouter(prefix="/api/v1", tags=["parent"])
_bearer = HTTPBearer(auto_error=False)

# Startup time for uptime calculation
_START_TIME = time.time()


async def _require_auth(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    if creds is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return verify_token(creds.credentials)


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ParentUser).where(ParentUser.email == body.email))
    user = result.scalars().first()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": str(user.user_id)})
    return TokenResponse(access_token=token)


# ── Register ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str


@router.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Reject duplicate emails
    existing = await db.execute(select(ParentUser).where(ParentUser.email == body.email))
    if existing.scalars().first() is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = ParentUser(
        email=body.email,
        hashed_password=get_password_hash(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token({"sub": str(user.user_id)})
    return TokenResponse(access_token=token)


# ── Devices ───────────────────────────────────────────────────────────────────

@router.get("/devices")
async def list_devices(
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(_require_auth),
):
    result = await db.execute(select(Device).where(Device.is_active == True))
    devices = result.scalars().all()
    return [{"device_id": str(d.device_id), "mac_address": d.mac_address, "label": d.label} for d in devices]


@router.get("/devices/{device_id}/position")
async def get_device_position(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(_require_auth),
):
    result = await db.execute(
        select(PositionEstimate)
        .where(PositionEstimate.device_id == device_id)
        .order_by(PositionEstimate.ts_server.desc())
        .limit(1)
    )
    pos = result.scalars().first()
    if pos is None:
        raise HTTPException(status_code=404, detail="No position data for device")
    return {
        "device_id": device_id,
        "x_m": pos.x_m,
        "y_m": pos.y_m,
        "source": pos.source,
        "confidence": pos.confidence,
        "active_aps": pos.active_aps,
        "mode": pos.mode,
    }


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    """PRD §14.4 health response."""
    # DB check
    db_status = "connected"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    result = await db.execute(select(Device).where(Device.is_active == True))
    active_count = len(result.scalars().all())

    return {
        "status": "healthy",
        "database": db_status,
        "fusion_engine": "running",   # ASSUMPTION: always "running" until coordinator is live
        "active_devices": active_count,
        "uptime_seconds": int(time.time() - _START_TIME),
    }
