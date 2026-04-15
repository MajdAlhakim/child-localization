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

Fusion pipeline:
  1. Run PDR on each IMU sample (continuous, 5 Hz).
  2. When Wi-Fi scan arrives (~every 10 s from Beetle scanner):
       a. Load APs from DB (cached 60 s).
       b. Run RSSI localizer (Kalman smooth + log-distance + WRLS multilateration).
       c. If ≥2 RSSI anchors: anchor PDR position to RSSI (prevents drift accumulation).
  3. Broadcast fused position via WebSocket.
"""

import logging
import os
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..fusion.device_state import DeviceState
from ..fusion.rssi_localizer import localize as rssi_localize
from ..fusion.tag_registry import registry
from ..core.broadcaster import broadcaster
from ..models import AccessPoint as APModel

logger = logging.getLogger("trakn.gateway")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)

router = APIRouter()

# ── Module-level device state registry ───────────────────────────────────────
# One DeviceState (with its own PDREngine) per MAC address.
device_states: dict[str, DeviceState] = {}

# ── AP cache — avoids DB hit on every packet ──────────────────────────────────
# Refreshed at most once per AP_CACHE_TTL seconds.
_ap_cache: list[dict] = []
_ap_cache_ts: float   = 0.0
_AP_CACHE_TTL: float  = 60.0   # seconds

# ── Minimum RSSI anchors needed before we snap PDR to RSSI ───────────────────
_MIN_RSSI_ANCHORS: int = 2


# ── Pydantic models ───────────────────────────────────────────────────────────

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


# ── AP cache helper ───────────────────────────────────────────────────────────

def _ap_to_dict(ap: APModel) -> dict:
    return {
        "bssid":        ap.bssid,
        "ssid":         ap.ssid,
        "rssi_ref":     ap.rssi_ref,
        "path_loss_n":  ap.path_loss_n,
        "x":            ap.x,
        "y":            ap.y,
    }

async def _refresh_ap_cache_if_stale(db: AsyncSession) -> None:
    """Reload all APs from DB if the cache is empty or older than AP_CACHE_TTL."""
    global _ap_cache, _ap_cache_ts
    if _ap_cache and (time.time() - _ap_cache_ts) < _AP_CACHE_TTL:
        return
    result = await db.execute(select(APModel))
    aps = result.scalars().all()
    _ap_cache = [_ap_to_dict(a) for a in aps]
    _ap_cache_ts = time.time()
    logger.info("AP cache refreshed — %d APs loaded", len(_ap_cache))


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/api/v1/gateway/packet", status_code=status.HTTP_200_OK)
async def receive_packet(
    packet: GatewayPacket,
    x_api_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Receive a packet from the ESP32-C5 tag, run PDR + RSSI fusion, return 200."""

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
        mac, packet.ts, len(imu), len(wifi),
    )
    for ap in wifi:
        logger.info(
            "  WIFI  bssid=%s  ssid=%-20s  rssi=%4d dBm  ch=%d",
            ap.bssid, ap.ssid, ap.rssi, ap.ch,
        )

    # ── Register MAC → tag_id and get/create device state ────────────────────
    tag_id = registry.register(mac)
    registry.touch(mac)
    if mac not in device_states:
        device_states[mac] = DeviceState(mac=mac)
        logger.info("  NEW device  mac=%s  tag_id=%s", mac, tag_id)
    state = device_states[mac]
    state.last_seen_ts = time.time()

    # ── RSSI localization (runs when Wi-Fi scan is present) ───────────────────
    rssi_result: dict | None = None
    if wifi:
        await _refresh_ap_cache_if_stale(db)
        if _ap_cache:
            scan = [{"bssid": ap.bssid, "rssi": ap.rssi} for ap in wifi]
            rssi_result = rssi_localize(scan, _ap_cache, state.kalman_states)
            if rssi_result:
                logger.info(
                    "  RSSI: x=%.2f y=%.2f anchors=%d err=%.1f dB",
                    rssi_result["x"], rssi_result["y"],
                    rssi_result["anchor_count"], rssi_result["avg_rssi_error"],
                )

    # ── Anchor PDR to RSSI when enough anchors are visible ───────────────────
    # This corrects PDR drift every ~10 s (Beetle scan interval).
    if rssi_result and rssi_result["anchor_count"] >= _MIN_RSSI_ANCHORS:
        state.pdr.x = rssi_result["x"]
        state.pdr.y = rssi_result["y"]
        logger.info(
            "  PDR anchored to RSSI: (%.2f, %.2f)", rssi_result["x"], rssi_result["y"]
        )

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
        if pdr_result["bias_calibrated"]:
            # Determine source and confidence for this broadcast
            if rssi_result and rssi_result["anchor_count"] >= _MIN_RSSI_ANCHORS:
                source     = "rssi_anchored"
                confidence = min(1.0, rssi_result["anchor_count"] / 5.0)
            else:
                source     = "pdr_only"
                confidence = 0.0

            msg = dict(pdr_result)
            msg["source"]        = source
            msg["mode"]          = "fused" if source == "rssi_anchored" else "imu_only"
            msg["confidence"]    = confidence
            msg["tag_id"]        = tag_id
            msg["rssi_anchors"]  = rssi_result["anchor_count"]   if rssi_result else None
            msg["rssi_error"]    = rssi_result["avg_rssi_error"] if rssi_result else None
            await broadcaster.broadcast(tag_id, msg)

    # ── Log PDR output ────────────────────────────────────────────────────────
    if pdr_result:
        logger.info(
            "  PDR: x=%.2f y=%.2f steps=%d cal=%s",
            pdr_result["x"], pdr_result["y"],
            pdr_result["step_count"], pdr_result["bias_calibrated"],
        )

    # ── Response ──────────────────────────────────────────────────────────────
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
        "rssi": rssi_result,
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
