import asyncio
import json
from datetime import datetime, timezone

from fastapi import WebSocket

# Max time to wait for a single ws.send_text — stale/half-dead clients must
# not block the gateway packet handler (which broadcasts per IMU sample).
_SEND_TIMEOUT_S = 0.5


class PositionBroadcaster:

    def __init__(self):
        # tag_id → set of active WebSocket connections
        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, tag_id: str, websocket: WebSocket) -> None:
        """Accept connection and register it."""
        await websocket.accept()
        if tag_id not in self._connections:
            self._connections[tag_id] = set()
        self._connections[tag_id].add(websocket)
        print(f"[WS] client connected for tag {tag_id} "
              f"({len(self._connections[tag_id])} total)")

    def disconnect(self, tag_id: str, websocket: WebSocket) -> None:
        """Remove a disconnected client."""
        if tag_id in self._connections:
            self._connections[tag_id].discard(websocket)
            if not self._connections[tag_id]:
                del self._connections[tag_id]
        print(f"[WS] client disconnected for tag {tag_id}")

    async def broadcast(self, tag_id: str, position: dict) -> None:
        """
        Push a position update to all subscribers of tag_id.
        Disconnected clients are silently removed.
        position dict comes directly from PDREngine._state() plus extra fields.
        """
        if tag_id not in self._connections:
            return   # no subscribers — nothing to do

        message = json.dumps({
            "tag_id":          tag_id,
            "x":               position.get("x", 0.0),
            "y":               position.get("y", 0.0),
            "heading":         position.get("heading", 0.0),
            "heading_deg":     position.get("heading_deg", 0.0),
            "step_count":      position.get("step_count", 0),
            "confidence":      position.get("confidence", 0.0),
            "source":          position.get("source", "pdr_only"),
            "mode":            position.get("mode", "imu_only"),
            "bias_calibrated": position.get("bias_calibrated", False),
            # RSSI localization info — None when no scan in this packet
            "rssi_anchors":    position.get("rssi_anchors"),
            "rssi_error":      position.get("rssi_error"),
            "ts":              datetime.now(timezone.utc).isoformat(),
        })

        # Send to all subscribers; collect any that fail
        dead: set[WebSocket] = set()
        for ws in set(self._connections[tag_id]):
            try:
                await asyncio.wait_for(ws.send_text(message), timeout=_SEND_TIMEOUT_S)
            except (asyncio.TimeoutError, Exception):
                dead.add(ws)

        # Clean up dead connections
        for ws in dead:
            self.disconnect(tag_id, ws)


# Module-level singleton — shared by gateway.py and websocket.py
broadcaster = PositionBroadcaster()
