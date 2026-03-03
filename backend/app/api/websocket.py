"""
backend/app/api/websocket.py
WebSocket broadcaster — TASK-14

Route:   WS /ws/position/{device_id}
Contract publish_position() interface (called by Person C's fusion coordinator):

    async def publish_position(
        device_id: str,
        position:  tuple[float, float],
        source:    str,
        confidence: float,
        active_aps: int,
        mode:      str,
    ) -> None

Wire format (locked — PRD §14.2 / workspace rules):
    {
        "device_id":  "<uuid>",
        "ts_utc":     "<ISO-8601>",
        "x_m":        <float>,
        "y_m":        <float>,
        "source":     "fused" | "wifi_only" | "imu_only",
        "confidence": <float>,
        "active_aps": <int>,
        "mode":       "normal" | "degraded" | "imu_only" | "disconnected"
    }

Person D owns this file.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# ── Connection registry ────────────────────────────────────────────────────────
# Maps device_id → set of active WebSocket connections subscribed to that device.
# A single device can have multiple concurrent subscribers (e.g. two parents).

class ConnectionManager:
    """Thread-safe WebSocket connection registry."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, device_id: str, ws: WebSocket) -> None:
        """Register a new subscriber for device_id."""
        await ws.accept()
        async with self._lock:
            if device_id not in self._subscribers:
                self._subscribers[device_id] = set()
            self._subscribers[device_id].add(ws)
        logger.info("WS connected: device=%s total_subs=%d", device_id,
                    len(self._subscribers[device_id]))

    async def disconnect(self, device_id: str, ws: WebSocket) -> None:
        """Remove a subscriber; clean up empty sets."""
        async with self._lock:
            subs = self._subscribers.get(device_id, set())
            subs.discard(ws)
            if not subs:
                self._subscribers.pop(device_id, None)
        logger.info("WS disconnected: device=%s", device_id)

    async def broadcast(self, device_id: str, message: str) -> None:
        """Send message to all current subscribers for device_id."""
        async with self._lock:
            subs = set(self._subscribers.get(device_id, set()))  # snapshot

        if not subs:
            return

        dead: list[WebSocket] = []
        for ws in subs:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        # Clean up any WebSockets that errored during send
        if dead:
            async with self._lock:
                for ws in dead:
                    self._subscribers.get(device_id, set()).discard(ws)


# Module-level singleton — shared across all requests
manager = ConnectionManager()


# ── publish_position() — the interface Person C calls ─────────────────────────

async def publish_position(
    device_id: str,
    position: tuple[float, float],
    source: str,
    confidence: float,
    active_aps: int,
    mode: str,
) -> None:
    """
    Broadcast a position update to all WebSocket subscribers for this device.

    Called by the fusion coordinator (Person C / TASK-13).
    Arguments must match the locked interface in workspace rules §8.

    Args:
        device_id:  UUID string identifying the tracked device.
        position:   (x_m, y_m) fused position in metres.
        source:     "fused" | "wifi_only" | "imu_only"
        confidence: Grid normalised confidence in [0, 1].
        active_aps: Number of APs that contributed to this estimate.
        mode:       "normal" | "degraded" | "imu_only" | "disconnected"
    """
    payload = {
        "device_id":  device_id,
        "ts_utc":     datetime.now(timezone.utc).isoformat(),
        "x_m":        float(position[0]),
        "y_m":        float(position[1]),
        "source":     source,
        "confidence": float(confidence),
        "active_aps": int(active_aps),
        "mode":       mode,
    }
    await manager.broadcast(device_id, json.dumps(payload))


# ── WebSocket endpoint ─────────────────────────────────────────────────────────

@router.websocket("/ws/position/{device_id}")
async def ws_position(websocket: WebSocket, device_id: str) -> None:
    """
    WebSocket endpoint for real-time position streaming.

    Clients connect to ws://<host>/ws/position/<device_id>.
    The server pushes position messages as JSON whenever publish_position()
    is called for that device_id.

    Client → server messages: ignored (one-way stream).
    """
    await manager.connect(device_id, websocket)
    try:
        while True:
            # Keep the connection alive; absorb any client-side pings/text.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(device_id, websocket)
