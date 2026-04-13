"""
backend/app/api/gateway.py

POST /api/v1/gateway/packet

Receives JSON packets from the XIAO ESP32-C5 tag.
Packet format:
{
    "mac":  "24:42:E3:15:E5:72",
    "ts":   12450,
    "imu":  [{"ts":.., "ax":.., "ay":.., "az":.., "gx":.., "gy":.., "gz":..}, ...],
    "wifi": [{"bssid":"..", "ssid":"..", "rssi":-46, "ch":6}, ...]
}

Milestone 1: validate API key, parse, log, return 200.
Milestone 2: run PDR engine on each IMU sample, return position in response.
"""

import logging
import os
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..fusion.device_state import DeviceState
from ..fusion.tag_registry import registry
from ..core.broadcaster import broadcaster

logger = logging.getLogger("trakn.gateway")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)

router = APIRouter()

# ── Module-level device state registry ───────────────────────────────────────
# One DeviceState (with its own PDREngine) per MAC address.
# Persists for the lifetime of the server process — no DB interaction.
device_states: dict[str, DeviceState] = {}


# ── Pydantic models  ────────────────────────────────────────────────

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
    """Receive a packet from the ESP32-C5 tag, run PDR, return 200 + position."""

    # ── Auth ──────────────────────────────────────────────────────────────────
    expected_key = os.environ.get("GATEWAY_API_KEY", "")
    if not x_api_key or x_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
        )

    mac  = packet.mac
    imu  = packet.imu
    wifi = packet.wifi

    # ── Log packet metadata ───────────────────────────────────────────────────
    logger.info(
        "PACKET  mac=%s  device_ts=%d ms  imu_samples=%d  wifi_aps=%d",
        mac,
        packet.ts,
        len(imu),
        len(wifi),
    )

    # ── Log each WiFi AP ──────────────────────────────────────────────────────
    for ap in wifi:
        logger.info(
            "  WIFI  bssid=%s  ssid=%-20s  rssi=%4d dBm  ch=%d",
            ap.bssid,
            ap.ssid,
            ap.rssi,
            ap.ch,
        )

    # ── Register MAC → tag_id and get/create device state ────────────────────
    tag_id = registry.register(mac)   # no-op if already known
    registry.touch(mac)
    if mac not in device_states:
        device_states[mac] = DeviceState(mac=mac)
        logger.info("  NEW device  mac=%s  tag_id=%s", mac, tag_id)
    state = device_states[mac]
    state.last_seen_ts = time.time()

    # ── Run PDR on each IMU sample — broadcast immediately once calibrated ────
    pdr_result = None
    for sample in imu:
        state.imu_buffer.append({
            "seq": state.imu_seq,
            "ts":  sample.ts,
            "ax":  sample.ax, "ay": sample.ay, "az": sample.az,
            "gx":  sample.gx, "gy": sample.gy, "gz": sample.gz,
        })
        state.imu_seq += 1
        pdr_result = state.pdr.ingest_sample(
            ts_ms = sample.ts,
            ax    = sample.ax,
            ay    = sample.ay,
            az    = sample.az,
            gx    = sample.gx,
            gy    = sample.gy,
            gz    = sample.gz,
        )
        # Broadcast per-sample once gyro bias is calibrated
        if pdr_result["bias_calibrated"]:
            msg = dict(pdr_result)
            msg["source"]     = "pdr_only"
            msg["mode"]       = "imu_only"
            msg["confidence"] = 0.0
            msg["tag_id"]     = tag_id
            await broadcaster.broadcast(tag_id, msg)

    # ── Log PDR output ────────────────────────────────────────────────────────
    if pdr_result:
        logger.info(
            "  PDR: x=%.2f y=%.2f steps=%d cal=%s",
            pdr_result["x"],
            pdr_result["y"],
            pdr_result["step_count"],
            pdr_result["bias_calibrated"],
        )

    # ── Response ──────────────────────────────────────────────────
    return {
        "status":      "ok",
        "mac":         mac,
        "imu_samples": len(imu),
        "wifi_aps":    len(wifi),
        "position": pdr_result if pdr_result else {
            "x": 0.0, "y": 0.0, "heading": 0.0,
            "heading_deg": 0.0, "step_count": 0,
            "bias_calibrated": False,
        },
    }


@router.get("/api/v1/position/{mac}", status_code=status.HTTP_200_OK)
async def get_position(mac: str) -> dict[str, Any]:
    """Return the current PDR position for a device (for local visualizers)."""
    state = device_states.get(mac)
    if state is None:
        return {"mac": mac, "known": False,
                "position": {"x": 0.0, "y": 0.0, "heading": 0.0,
                             "heading_deg": 0.0, "step_count": 0,
                             "bias_calibrated": False}}
    pos = state.pdr._state()
    return {"mac": mac, "known": True, "last_seen_ts": state.last_seen_ts,
            "position": pos}


@router.get("/api/v1/imu/{mac}", status_code=status.HTTP_200_OK)
async def get_imu_samples(mac: str, since: int = 0) -> dict[str, Any]:
    """
    Return raw IMU samples buffered since sequence number `since`.
    Used by the local Python visualizer to replay samples exactly as
    MATLAB reads them from the COM port — but via HTTP instead.
    """
    state = device_states.get(mac)
    if state is None:
        return {"mac": mac, "samples": [], "next_seq": 0}
    samples = [s for s in state.imu_buffer if s["seq"] >= since]
    return {"mac": mac, "samples": samples, "next_seq": state.imu_seq}
