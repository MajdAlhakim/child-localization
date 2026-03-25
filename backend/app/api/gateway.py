"""
backend/app/api/gateway.py

POST /api/v1/gateway/packet — Device gateway endpoint.

Receives direct HTTPS POSTs from the XIAO ESP32-C5 wearable (over QU-User Wi-Fi).
Authenticates via X-API-Key header, parses the JSON body, persists IMU samples and
Wi-Fi RSSI observations to the database, and forwards IMU data to the fusion coordinator.

Wire format: JSON — see firmware/esp32c5/trakn_tag/trakn_tag.ino for schema.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.security import verify_gateway_key
from backend.app.db.models import AccessPoint, Device, ImuSample, RttMeasurement
from backend.app.db.session import get_db
from backend.app.schemas.gateway import (
    GatewayPacketRequest,
    GatewayPacketResponse,
    ImuSampleIn,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/gateway", tags=["gateway"])


# ── Dependency: extract and validate the X-API-Key header ────────────────────

async def _require_api_key(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> None:
    """FastAPI dependency — raises 401 if key is missing or invalid."""
    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header is required",
        )
    verify_gateway_key(x_api_key)


# ── Helper: look up or auto-create a Device row ───────────────────────────────

async def _get_or_create_device(mac: str, db: AsyncSession) -> Device:
    """Return the Device for the given MAC, creating it if not seen before."""
    result = await db.execute(select(Device).where(Device.mac_address == mac))
    device = result.scalar_one_or_none()
    if device is None:
        device = Device(mac_address=mac, label=f"ESP32C5-{mac}", is_active=True)
        db.add(device)
        await db.flush()
    return device


# ── POST /api/v1/gateway/packet ───────────────────────────────────────────────

@router.post(
    "/packet",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GatewayPacketResponse,
    dependencies=[Depends(_require_api_key)],
    summary="Receive JSON IMU + Wi-Fi RSSI packet from XIAO ESP32-C5 device",
)
async def receive_packet(
    body: GatewayPacketRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> GatewayPacketResponse:
    """
    Accepts a direct HTTPS POST from the XIAO ESP32-C5.

    Flow:
      1. Verify X-API-Key (handled by dependency).
      2. Parse JSON packet body.
      3. Look up / create Device row.
      4. Persist each IMU sample to imu_samples.
      5. Persist each Wi-Fi AP entry to rtt_measurements (RSSI only; no RTT distances
         available on ESP32-C5 — d_raw_mean_m and d_raw_std_m are stored as NULL).
      6. Forward IMU samples to fusion coordinator (fire-and-forget, best-effort).
      7. Return 202 Accepted.
    """
    # Step 3 — device lookup / creation
    device = await _get_or_create_device(body.mac, db)

    # Step 4 — persist IMU samples (seq not provided by ESP32-C5 firmware)
    for s in body.imu:
        sample = ImuSample(
            device_id=device.device_id,
            ts_device_ms=s.ts,
            ax_ms2=s.ax,
            ay_ms2=s.ay,
            az_ms2=s.az,
            gx_rads=s.gx,
            gy_rads=s.gy,
            gz_rads=s.gz,
            seq=None,
        )
        db.add(sample)

    # Step 5 — persist Wi-Fi RSSI scan results
    for ap_entry in body.wifi:
        result = await db.execute(
            select(AccessPoint).where(AccessPoint.bssid == ap_entry.bssid)
        )
        ap_row = result.scalar_one_or_none()
        if ap_row is None:
            band = "2.4GHz" if ap_entry.ch <= 14 else "5GHz"
            ap_row = AccessPoint(
                bssid=ap_entry.bssid,
                ssid=ap_entry.ssid,
                band=band,
            )
            db.add(ap_row)
            await db.flush()

        band = "2.4GHz" if ap_entry.ch <= 14 else "5GHz"
        meas = RttMeasurement(
            device_id=device.device_id,
            ap_id=ap_row.ap_id,
            ts_device_ms=body.ts,
            d_raw_mean_m=None,   # Wi-Fi RTT not available on ESP32-C5; RSSI scan only
            d_raw_std_m=None,
            rssi_dbm=ap_entry.rssi,
            band=band,
        )
        db.add(meas)

    await db.commit()

    # Step 6 — forward IMU to fusion coordinator
    if body.imu:
        await _forward_imu(request, body.imu, str(device.device_id))

    return GatewayPacketResponse(
        status="accepted",
        imu_count=len(body.imu),
        wifi_count=len(body.wifi),
        device_mac=body.mac,
    )


# ── Coordinator forwarding helpers ────────────────────────────────────────────

async def _forward_imu(
    request: Request,
    samples: list[ImuSampleIn],
    _device_id: str,
) -> None:
    """Forward each IMU sample to the fusion coordinator if one is registered."""
    coordinator = getattr(request.app.state, "coordinator", None)
    if coordinator is None:
        return
    for s in samples:
        try:
            await coordinator.on_imu(
                ax=s.ax,
                ay=s.ay,
                az=s.az,
                gz=s.gz,
                t=s.ts / 1000.0,
                dt=0.01,  # 100 Hz nominal
            )
        except Exception:
            logger.exception("IMU forwarding to coordinator failed — continuing")
