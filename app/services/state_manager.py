import asyncio
import logging
from enum import Enum
from typing import Dict, Any, Set, Optional
from datetime import datetime
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class HealthStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    TESTING = "TESTING"
    CONNECTED = "CONNECTED"
    FAILED = "FAILED"
    DISABLED = "DISABLED"

class StateManager:
    """
    시스템 전체의 유일한 Single Source of Truth 상태 관리자
    카메라별 VISCA / RTSP 분리 런타임 상태 관리 및 WebSocket 실시간 브로드캐스트
    """

    def __init__(self):
        # camera_id -> {"visca": HealthStatus, "rtsp": HealthStatus, "last_checked": str, "last_error": str}
        self.camera_runtime_states: Dict[int, Dict[str, Any]] = {}
        self.preset_statuses: Dict[int, str] = {}
        self.system_status: str = "READY"
        
        self.active_websockets: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def register_websocket(self, websocket: WebSocket):
        await websocket.accept()
        self.active_websockets.add(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_websockets)}")

    async def unregister_websocket(self, websocket: WebSocket):
        self.active_websockets.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_websockets)}")

    async def broadcast_event(self, event_type: str, data: Dict[str, Any]):
        message = {
            "type": event_type,
            "payload": data
        }
        disconnected = set()
        for ws in self.active_websockets:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send websocket message: {e}")
                disconnected.add(ws)

        for ws in disconnected:
            self.active_websockets.discard(ws)

    async def update_camera_health(
        self,
        camera_id: int,
        visca_status: HealthStatus,
        rtsp_status: HealthStatus,
        visca_latency_ms: Optional[float] = None,
        rtsp_resolution: Optional[str] = None,
        error_msg: Optional[str] = None
    ):
        """카메라 VISCA & RTSP 2단계 런타임 상태 업데이트"""
        now_str = datetime.now().strftime("%H:%M:%S")
        async with self._lock:
            state = {
                "visca_status": visca_status.value if isinstance(visca_status, HealthStatus) else visca_status,
                "rtsp_status": rtsp_status.value if isinstance(rtsp_status, HealthStatus) else rtsp_status,
                "visca_latency_ms": visca_latency_ms,
                "rtsp_resolution": rtsp_resolution,
                "last_checked_at": now_str,
                "last_error": error_msg
            }
            self.camera_runtime_states[camera_id] = state

            await self.broadcast_event("camera_health_update", {
                "camera_id": camera_id,
                **state
            })

    async def update_preset_status(self, camera_id: int, preset_id: int, status: str, error_msg: str = None):
        async with self._lock:
            self.preset_statuses[preset_id] = status
            await self.broadcast_event("preset_status", {
                "camera_id": camera_id,
                "preset_id": preset_id,
                "status": status,
                "error_message": error_msg
            })

state_manager = StateManager()
