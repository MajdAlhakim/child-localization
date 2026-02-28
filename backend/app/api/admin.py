"""Admin API — calibration data management. Protected by JWT Bearer auth.

PRD §10.4:
    POST   /api/v1/admin/calibration
    GET    /api/v1/admin/calibration
    GET    /api/v1/admin/calibration/{bssid}
    DELETE /api/v1/admin/calibration/{bssid}

Reliability rule (PRD §10.3):
    is_reliable = False  if std_dev_m > 20 OR sample_count < 30
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.security import verify_token
from backend.app.db.models import AccessPoint, ApCalibration
from backend.app.db.session import get_db

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
_bearer = HTTPBearer()


async def _require_auth(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    return verify_token(creds.credentials)


# ── Request / Response schemas ────────────────────────────────────────────────

class CalibrationIn(BaseModel):
    bssid: str
    band: str          # "2.4GHz" or "5GHz"
    offset_m: float
    std_dev_m: float
    sample_count: int


class CalibrationOut(BaseModel):
    bssid: str
    band: str
    offset_m: float
    std_dev_m: float
    sample_count: int
    is_reliable: bool

    class Config:
        from_attributes = True


def _is_reliable(std_dev_m: float, sample_count: int) -> bool:
    """PRD §10.3 reliability gate."""
    return std_dev_m <= 20.0 and sample_count >= 30


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/calibration", status_code=status.HTTP_201_CREATED, response_model=CalibrationOut)
async def create_calibration(
    body: CalibrationIn,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(_require_auth),
):
    """Create or update calibration entry for an AP+band pair."""
    # Upsert access_point record
    result = await db.execute(select(AccessPoint).where(AccessPoint.bssid == body.bssid))
    ap = result.scalars().first()
    if ap is None:
        ap = AccessPoint(bssid=body.bssid)
        db.add(ap)
        await db.flush()

    # Check for existing calibration entry for this AP+band
    result = await db.execute(
        select(ApCalibration).where(
            ApCalibration.ap_id == ap.ap_id,
            ApCalibration.band == body.band,
        )
    )
    cal = result.scalars().first()
    if cal is None:
        cal = ApCalibration(ap_id=ap.ap_id)
        db.add(cal)

    cal.band = body.band
    cal.offset_m = body.offset_m
    cal.std_dev_m = body.std_dev_m
    cal.sample_count = body.sample_count
    cal.is_reliable = _is_reliable(body.std_dev_m, body.sample_count)

    await db.commit()
    await db.refresh(cal)

    return CalibrationOut(
        bssid=body.bssid,
        band=cal.band,
        offset_m=cal.offset_m,
        std_dev_m=cal.std_dev_m,
        sample_count=cal.sample_count,
        is_reliable=cal.is_reliable,
    )


@router.get("/calibration", response_model=list[CalibrationOut])
async def list_calibration(
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(_require_auth),
):
    result = await db.execute(
        select(ApCalibration, AccessPoint.bssid)
        .join(AccessPoint, ApCalibration.ap_id == AccessPoint.ap_id)
    )
    rows = result.all()
    return [
        CalibrationOut(
            bssid=bssid,
            band=cal.band,
            offset_m=cal.offset_m,
            std_dev_m=cal.std_dev_m,
            sample_count=cal.sample_count,
            is_reliable=cal.is_reliable,
        )
        for cal, bssid in rows
    ]


@router.get("/calibration/{bssid}", response_model=CalibrationOut)
async def get_calibration(
    bssid: str,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(_require_auth),
):
    result = await db.execute(
        select(ApCalibration, AccessPoint.bssid)
        .join(AccessPoint, ApCalibration.ap_id == AccessPoint.ap_id)
        .where(AccessPoint.bssid == bssid)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No calibration for {bssid}")
    cal, bssid_val = row
    return CalibrationOut(
        bssid=bssid_val,
        band=cal.band,
        offset_m=cal.offset_m,
        std_dev_m=cal.std_dev_m,
        sample_count=cal.sample_count,
        is_reliable=cal.is_reliable,
    )


@router.delete("/calibration/{bssid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calibration(
    bssid: str,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(_require_auth),
):
    result = await db.execute(select(AccessPoint).where(AccessPoint.bssid == bssid))
    ap = result.scalars().first()
    if ap is None:
        raise HTTPException(status_code=404, detail=f"No AP with bssid {bssid}")
    await db.execute(delete(ApCalibration).where(ApCalibration.ap_id == ap.ap_id))
    await db.commit()
