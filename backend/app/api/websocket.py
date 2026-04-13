from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.broadcaster import broadcaster
from ..fusion.tag_registry import registry

router = APIRouter()


@router.websocket("/ws/position/{tag_id}")
async def position_stream(websocket: WebSocket, tag_id: str):
    """
    Real-time position stream for a specific tag.

    tag_id must be a registered TRAKN-XXXX ID (assigned when the device first
    connects). Clients obtain it by scanning the QR code on the physical tag
    or from GET /api/v1/tags.

    Rejects unknown tag IDs with WebSocket close code 4004 so the Flutter
    app can show a meaningful "Tag not found" error instead of silently
    failing to receive updates.
    """
    if registry.get(tag_id) is None:
        await websocket.close(code=4004, reason=f"Tag {tag_id!r} not registered")
        return

    await broadcaster.connect(tag_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        broadcaster.disconnect(tag_id, websocket)
    except Exception:
        broadcaster.disconnect(tag_id, websocket)
