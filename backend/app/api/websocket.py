from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.broadcaster import broadcaster

router = APIRouter()


@router.websocket("/ws/position/{tag_id}")
async def position_stream(websocket: WebSocket, tag_id: str):
    """
    Real-time position stream for a specific tag (PRD §5.3, §16.2).

    Client connects and receives position updates as they arrive from the device.
    Connection closes cleanly on client disconnect.

    tag_id: unique tag identifier (e.g. "TRAKN-0042")
            In dev/testing use the device MAC as tag_id:
            ws://35.238.189.188/ws/position/24:42:E3:15:E5:72
    """
    await broadcaster.connect(tag_id, websocket)
    try:
        # Keep connection open — we do not receive messages from the client
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        broadcaster.disconnect(tag_id, websocket)
    except Exception:
        broadcaster.disconnect(tag_id, websocket)
