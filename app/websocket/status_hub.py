from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.state_manager import state_manager

router = APIRouter()

@router.websocket("/ws/status")
async def websocket_status_endpoint(websocket: WebSocket):
    await state_manager.register_websocket(websocket)
    try:
        while True:
            # Client heartbeat/messages
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        await state_manager.unregister_websocket(websocket)
