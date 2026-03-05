"""
backend/app/api/gateway.py

POST /api/v1/gateway/packet — Device gateway endpoint.

Receives direct HTTPS POSTs from the BW16 wearable device (over QU-User Wi-Fi).
Authenticates via X-API-Key header, base64-decodes the binary payload,
routes to the packet parser, persists to the database, and forwards to the
fusion coordinator.

Wire format: see workspace rules §8 / PRD §14.1.
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core import ble_parser
from backend.app.core.security import verify_gateway_key
from backend.app.db.models import Device, ImuSample, RttMeasurement, AccessPoint
from backend.app.db.session import get_db
from backend.app.schemas.gateway import GatewayPacketRequest, GatewayPacketResponse

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
        device = Device(mac_address=mac, label=f"BW16-{mac}", is_active=True)
        db.add(device)
        await db.flush()  # populate device_id without committing
    return device


# ── POST /api/v1/gateway/packet ───────────────────────────────────────────────

@router.post(
    "/packet",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GatewayPacketResponse,
    dependencies=[Depends(_require_api_key)],
    summary="Receive binary IMU or RTT packet from BW16 device",
)
async def receive_packet(
    body: GatewayPacketRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> GatewayPacketResponse:
    """
    Accepts a direct HTTPS POST from the BW16.

    Flow:
      1. Verify X-API-Key (handled by dependency).
      2. Base64-decode payload_b64.
      3. Parse binary packet (Type 0x01 IMU or 0x02 RTT).
      4. Look up / create Device row.
      5. Persist sample to imu_samples or rtt_measurements.
      6. Forward to fusion coordinator (fire-and-forget, best-effort).
      7. Return 202 Accepted.
    """
    # Step 2 — base64 decode
    try:
        raw_bytes = base64.b64decode(body.payload_b64, validate=True)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payload_b64 is not valid base64",
        )

    # Step 3 — parse binary packet
    try:
        packet = ble_parser.parse(raw_bytes)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Packet parse error: {exc}",
        )

    # Step 4 — device lookup / creation
    device = await _get_or_create_device(body.device_mac, db)

    # Step 5 — persist
    if isinstance(packet, ble_parser.ImuPacket):
        sample = ImuSample(
            device_id=device.device_id,
            ts_device_ms=packet.ts_ms,
            ax_ms2=packet.ax_ms2,
            ay_ms2=packet.ay_ms2,
            az_ms2=packet.az_ms2,
            gx_rads=packet.gx_rads,
            gy_rads=packet.gy_rads,
            gz_rads=packet.gz_rads,
            seq=packet.seq,
        )
        db.add(sample)
        await db.commit()

        # Step 6 — forward to fusion coordinator
        await _forward_imu(request, packet, body.rx_ts_utc, str(device.device_id))

    elif isinstance(packet, ble_parser.RttPacket):
        # Persist each AP measurement; skip APs not yet registered (OQ-03)
        for ap_rec in packet.measurements:
            result = await db.execute(
                select(AccessPoint).where(AccessPoint.bssid == ap_rec.bssid)
            )
            ap_row = result.scalar_one_or_none()
            if ap_row is None:
                # AP not yet registered — persist without AP-FK by creating it
                ap_row = AccessPoint(bssid=ap_rec.bssid, band=ap_rec.band)
                db.add(ap_row)
                await db.flush()

            meas = RttMeasurement(
                device_id=device.device_id,
                ap_id=ap_row.ap_id,
                ts_device_ms=packet.ts_ms,
                d_raw_mean_m=ap_rec.d_raw_mean,
                d_raw_std_m=ap_rec.d_raw_std,
                rssi_dbm=ap_rec.rssi,
                band=ap_rec.band,
            )
            db.add(meas)

        await db.commit()

        # Step 6 — forward to fusion coordinator
        await _forward_rtt(request, packet, str(device.device_id))

    return GatewayPacketResponse(
        status="accepted",
        packet_type=packet.packet_type,
        device_mac=body.device_mac,
    )


# ── Coordinator forwarding helpers ────────────────────────────────────────────

async def _forward_imu(
    request: Request,
    packet: ble_parser.ImuPacket,
    rx_ts: datetime,
    device_id: str,
) -> None:
    """Forward IMU data to the fusion coordinator if one is registered."""
    coordinator = getattr(request.app.state, "coordinator", None)
    if coordinator is None:
        return
    try:
        # dt is approximated from rx_ts (device clock not synchronised with server)
        t = packet.ts_ms / 1000.0
        dt = 0.01  # 100 Hz nominal; coordinator uses this for EKF predict
        await coordinator.on_imu(
            ax=packet.ax_ms2,
            ay=packet.ay_ms2,
            az=packet.az_ms2,
            gz=packet.gz_rads,
            t=t,
            dt=dt,
        )
    except Exception:
        logger.exception("IMU forwarding to coordinator failed — continuing")


async def _forward_rtt(
    request: Request,
    packet: ble_parser.RttPacket,
    device_id: str,
) -> None:
    """Forward RTT measurements to the fusion coordinator if one is registered."""
    coordinator = getattr(request.app.state, "coordinator", None)
    if coordinator is None:
        return
    try:
        measurements = [
            {
                "bssid": ap.bssid,
                "d_raw_mean": ap.d_raw_mean,
                "d_raw_std": ap.d_raw_std,
                "rssi": ap.rssi,
                "band": ap.band,
            }
            for ap in packet.measurements
        ]
        await coordinator.on_rtt(measurements)
    except Exception:
        logger.exception("RTT forwarding to coordinator failed — continuing")
