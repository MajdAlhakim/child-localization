"""
backend/app/api/gateway.py

POST /api/v1/gateway/packet

Receives JSON packets from the XIAO ESP32-C5 tag.
Packet format (PRD §6.5 / §16.1):
{
    "mac":  "24:42:E3:15:E5:72",
    "ts":   12450,
    "imu":  [{"ts":..,"ax":..,"ay":..,"az":..,"gx":..,"gy":..,"gz":..}, ...],
    "wifi": [{"bssid":"..","ssid":"..","rssi":-46,"ch":6}, ...]
}

This milestone: validate API key, parse, log to stdout, return 200.
No database writes. No PDR. No positioning.
"""

import logging
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

logger = logging.getLogger("trakn.gateway")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)

router = APIRouter()

# ── Pydantic models (PRD §6.5) ────────────────────────────────────────────────

class ImuSample(BaseModel):
    ts: int            # device milliseconds
    ax: float          # m/s²
    ay: float
    az: float
    gx: float          # rad/s
    gy: float
    gz: float


class WifiAP(BaseModel):
    bssid: str
    ssid:  str
    rssi:  int         # dBm
    ch:    int         # channel


class GatewayPacket(BaseModel):
    mac:  str
    ts:   int                        # device milliseconds since boot
    imu:  list[ImuSample] = Field(default_factory=list)
    wifi: list[WifiAP]   = Field(default_factory=list)


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/api/v1/gateway/packet", status_code=status.HTTP_200_OK)
async def receive_packet(
    packet: GatewayPacket,
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    """Receive a packet from the ESP32 tag, log it, return 200."""

    # ── Auth ──────────────────────────────────────────────────────────────────
    expected_key = os.environ.get("GATEWAY_API_KEY", "")
    if not x_api_key or x_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
        )

    # ── Log packet metadata ───────────────────────────────────────────────────
    logger.info(
        "PACKET  mac=%s  device_ts=%d ms  imu_samples=%d  wifi_aps=%d",
        packet.mac,
        packet.ts,
        len(packet.imu),
        len(packet.wifi),
    )

    # ── Log each WiFi AP ──────────────────────────────────────────────────────
    for ap in packet.wifi:
        logger.info(
            "  WIFI  bssid=%s  ssid=%-20s  rssi=%4d dBm  ch=%d",
            ap.bssid,
            ap.ssid,
            ap.rssi,
            ap.ch,
        )

    # ── Response (PRD §16.1) ──────────────────────────────────────────────────
    return {
        "status":      "ok",
        "mac":         packet.mac,
        "imu_samples": len(packet.imu),
        "wifi_aps":    len(packet.wifi),
    }
