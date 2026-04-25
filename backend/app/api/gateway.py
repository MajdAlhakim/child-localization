"""
backend/app/api/gateway.py

POST /api/v1/gateway/packet

Receives JSON packets from the Beetle ESP32-C6 tag.
Packet format:
{
    "mac":  "9C:9E:6E:77:17:50",
    "ts":   12450,
    "imu":  [{"ts":.., "ax":.., "ay":.., "az":.., "gx":.., "gy":.., "gz":..}, ...],
    "wifi": [{"bssid":"..", "ssid":"..", "rssi":-46, "ch":6}, ...]
}

Fusion pipeline:
  1. Run PDR on each IMU sample (continuous, 5 Hz).
  2. When Wi-Fi scan arrives (~every 5 s from Beetle scanner):
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
from ..models import AccessPoint as APModel, FloorPlan as FPModel

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
_MIN_RSSI_ANCHORS: int = 1


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
    mac:   str
    ts:    int                        # device milliseconds since boot
    imu:   list[ImuSample] = Field(default_factory=list)
    wifi:  list[WifiAP]   = Field(default_factory=list)
    floor: int | None = None          # barometer floor estimate from firmware (-1/0/1/2)


# ── AP cache helper ───────────────────────────────────────────────────────────

def _ap_to_dict(ap: APModel, floor_number: int) -> dict:
    return {
        "bssid":          ap.bssid,
        "ssid":           ap.ssid,
        "rssi_ref":       ap.rssi_ref,
        "path_loss_n":    ap.path_loss_n,
        "x":              ap.x,
        "y":              ap.y,
        "floor_plan_id":  str(ap.floor_plan_id),
        "floor_number":   floor_number,
    }

async def _refresh_ap_cache_if_stale(db: AsyncSession) -> None:
    """Reload all APs from DB if the cache is empty or older than AP_CACHE_TTL."""
    global _ap_cache, _ap_cache_ts
    if _ap_cache and (time.time() - _ap_cache_ts) < _AP_CACHE_TTL:
        return
    result = await db.execute(
        select(APModel, FPModel.floor_number)
        .join(FPModel, APModel.floor_plan_id == FPModel.id)
    )
    _ap_cache = [_ap_to_dict(ap, floor_number) for ap, floor_number in result.all()]
    _ap_cache_ts = time.time()
    logger.info(
        "AP cache refreshed — %d APs across %d floor plans",
        len(_ap_cache),
        len({e["floor_plan_id"] for e in _ap_cache}),
    )


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/api/v1/gateway/packet", status_code=status.HTTP_200_OK)
async def receive_packet(
    packet: GatewayPacket,
    x_api_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Receive a packet from the Beetle C6 tag, run PDR + RSSI fusion, return 200."""

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

    # ── RSSI localization + floor determination ───────────────────────────────
    # Floor priority: barometer (packet.floor) > BSSID majority vote.
    # BSSID voting is only used as a fallback when no barometer data arrives.
    rssi_result: dict | None = None
    if wifi:
        await _refresh_ap_cache_if_stale(db)
        if _ap_cache:
            scan = [{"bssid": ap.bssid, "rssi": ap.rssi} for ap in wifi]
            rssi_result = rssi_localize(scan, _ap_cache, state.kalman_states)
            if rssi_result:
                state.last_rssi_result = rssi_result   # cache for heartbeat broadcasts
                logger.info(
                    "  RSSI: x=%.2f y=%.2f anchors=%d err=%.1f dB",
                    rssi_result["x"], rssi_result["y"],
                    rssi_result["anchor_count"], rssi_result["avg_rssi_error"],
                )

            # BSSID majority-vote floor — only when barometer is not available
            if packet.floor is None and _ap_cache:
                scan_bssids = {ap.bssid.lower() for ap in wifi}
                floor_votes: dict[str, int] = {}
                floor_number_map: dict[str, int] = {}
                for entry in _ap_cache:
                    if entry["bssid"].lower() in scan_bssids:
                        fp_id = entry["floor_plan_id"]
                        floor_votes[fp_id] = floor_votes.get(fp_id, 0) + 1
                        floor_number_map[fp_id] = entry["floor_number"]
                if floor_votes:
                    best_fp_id = max(floor_votes, key=lambda k: floor_votes[k])
                    state.active_floor_plan_id = best_fp_id
                    state.active_floor_number  = floor_number_map[best_fp_id]
                    logger.info(
                        "  Floor (BSSID fallback): floor_plan_id=%s floor_number=%d (votes=%s)",
                        best_fp_id, state.active_floor_number, floor_votes,
                    )

    # ── Barometer floor (highest priority — always wins over BSSID vote) ──────
    if packet.floor is not None:
        if not wifi:
            await _refresh_ap_cache_if_stale(db)

        # Map firmware floor index to DB floor_number.
        # Firmware is 0-indexed (ground=0, 1st above=1, …).
        # DB floor_number is whatever the user assigned in the web tool (e.g. 1,2).
        # Offset = min DB floor_number so firmware-0 always aligns with the
        # lowest floor in the database, regardless of user-chosen numbering.
        db_floor_numbers = sorted({e["floor_number"] for e in _ap_cache}) if _ap_cache else []
        if db_floor_numbers:
            offset = db_floor_numbers[0]          # e.g. 1 if floors are [1,2]
            mapped_floor = packet.floor + offset
        else:
            mapped_floor = packet.floor           # no AP data yet, use raw value

        state.active_floor_number = mapped_floor
        for entry in _ap_cache:
            if entry["floor_number"] == mapped_floor:
                state.active_floor_plan_id = entry["floor_plan_id"]
                break
        logger.info(
            "  Floor (barometer): firmware=%d offset=%d mapped=%d floor_plan_id=%s",
            packet.floor, offset if db_floor_numbers else 0,
            mapped_floor, state.active_floor_plan_id,
        )

    # Use fresh RSSI result from this packet, or fall back to last cached result
    # so the broadcast fires on every packet (heartbeat at ~5 Hz) rather than
    # only on the ~5 s Wi-Fi scan interval.
    effective_rssi = rssi_result or state.last_rssi_result

    # ── Anchor PDR dead-reckoning to RSSI absolute position ──────────────────
    # PDR accumulates heading + step count; RSSI corrects absolute x,y every ~5 s.
    # This is the fusion step: RSSI dominates position, PDR dominates heading.
    # Only anchor on a fresh scan (rssi_result), not the cached fallback.
    if rssi_result and rssi_result["anchor_count"] >= _MIN_RSSI_ANCHORS:
        state.pdr.x = rssi_result["x"]
        state.pdr.y = rssi_result["y"]
        logger.info(
            "  PDR anchored to RSSI: (%.2f, %.2f)", rssi_result["x"], rssi_result["y"]
        )

    # ── Run PDR on each IMU sample (accumulates heading + steps) ─────────────
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

    if pdr_result:
        logger.info(
            "  PDR: x=%.2f y=%.2f steps=%d cal=%s heading=%.1f°",
            pdr_result["x"], pdr_result["y"],
            pdr_result["step_count"], pdr_result["bias_calibrated"],
            pdr_result.get("heading_deg", 0.0),
        )

    # ── Broadcast fused position on every packet ─────────────────────────────
    # Position (x, y) from RSSI; heading and step count from PDR.
    # Uses effective_rssi (fresh scan or last cached) so broadcasts fire at the
    # full packet rate (~5 Hz) rather than only on the 5 s scan interval.
    if effective_rssi:
        confidence = min(1.0, effective_rssi["anchor_count"] / 5.0)
        msg = {
            "x":              effective_rssi["x"],
            "y":              effective_rssi["y"],
            "heading":        pdr_result.get("heading", 0.0)       if pdr_result else 0.0,
            "heading_deg":    pdr_result.get("heading_deg", 0.0)   if pdr_result else 0.0,
            "step_count":     pdr_result.get("step_count", 0)      if pdr_result else 0,
            "bias_calibrated": True,
            "source":         "fused",
            "mode":           "fused",
            "confidence":     confidence,
            "tag_id":         tag_id,
            "rssi_anchors":   effective_rssi["anchor_count"],
            "rssi_error":     effective_rssi["avg_rssi_error"],
            "floor_plan_id":  state.active_floor_plan_id,
            "floor_number":   state.active_floor_number,
        }
        await broadcaster.broadcast(tag_id, msg)

    # ── Response ──────────────────────────────────────────────────────────────
    return {
        "status":      "ok",
        "mac":         mac,
        "imu_samples": len(imu),
        "wifi_aps":    len(wifi),
        "position": {
            "x":              effective_rssi["x"]                       if effective_rssi else 0.0,
            "y":              effective_rssi["y"]                       if effective_rssi else 0.0,
            "heading":        pdr_result.get("heading", 0.0)           if pdr_result else 0.0,
            "heading_deg":    pdr_result.get("heading_deg", 0.0)       if pdr_result else 0.0,
            "step_count":     pdr_result.get("step_count", 0)          if pdr_result else 0,
            "bias_calibrated": bool(effective_rssi),
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
