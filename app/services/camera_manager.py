import asyncio
import logging
from typing import Dict, Set, Optional, Any
from app.services.ptz.visca import ViscaController
from app.services.ptz.guard import ProtectedPTZController
from app.database import get_db_connection

logger = logging.getLogger(__name__)

class CameraManager:
    """
    카메라별 비동기 락(Async Lock), health_check_lock 및 ProtectedPTZController 관리기
    원자적(Atomic) reload_camera 스왑 지원
    """

    def __init__(self):
        self._locks: Dict[int, asyncio.Lock] = {}
        self._health_locks: Dict[int, asyncio.Lock] = {}
        self._controllers: Dict[int, ProtectedPTZController] = {}

    def get_lock(self, camera_id: int) -> asyncio.Lock:
        if camera_id not in self._locks:
            self._locks[camera_id] = asyncio.Lock()
        return self._locks[camera_id]

    def get_health_lock(self, camera_id: int) -> asyncio.Lock:
        if camera_id not in self._health_locks:
            self._health_locks[camera_id] = asyncio.Lock()
        return self._health_locks[camera_id]

    def get_protected_controller(self, camera_id: int) -> Optional[ProtectedPTZController]:
        if camera_id in self._controllers:
            return self._controllers[camera_id]

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ip_address, visca_port, visca_protocol FROM cameras WHERE id = ?", (camera_id,))
        cam_row = cursor.fetchone()
        if not cam_row:
            conn.close()
            return None

        cursor.execute("SELECT base_preset_no FROM presets WHERE camera_id = ?", (camera_id,))
        base_rows = cursor.fetchall()
        conn.close()

        protected_base_presets = {r["base_preset_no"] for r in base_rows}

        raw_visca = ViscaController(
            ip=cam_row["ip_address"],
            port=cam_row["visca_port"],
            protocol=cam_row["visca_protocol"]
        )
        protected_controller = ProtectedPTZController(raw_visca, protected_base_presets)
        self._controllers[camera_id] = protected_controller
        return protected_controller

    async def atomic_reload_camera(self, camera_id: int, new_config: Dict[str, Any]) -> bool:
        """
        [ATOMIC SWAP]
        새 설정으로 신규 PTZController 사전검증 및 생성을 먼저 시도한 후 
        성공 시 기존 컨트롤러를 닫고 스왑 (Old -> New)
        """
        async with self.get_lock(camera_id):
            logger.info(f"Initiating Atomic Reload for Camera #{camera_id}")
            try:
                new_raw = ViscaController(
                    ip=new_config["ip_address"],
                    port=new_config["visca_port"],
                    protocol=new_config["visca_protocol"]
                )
                conn_ok = await new_raw.connect()
                if not conn_ok:
                    logger.warning(f"Atomic Reload aborted for Camera #{camera_id}: Failed to connect with new config")
                    return False

                # 새 연결 확보 성공 -> 기존 커넥션 안전 종료 후 스왑
                if camera_id in self._controllers:
                    old_controller = self._controllers[camera_id]
                    await old_controller.disconnect()

                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT base_preset_no FROM presets WHERE camera_id = ?", (camera_id,))
                base_rows = cursor.fetchall()
                conn.close()

                protected_base_presets = {r["base_preset_no"] for r in base_rows}
                self._controllers[camera_id] = ProtectedPTZController(new_raw, protected_base_presets)

                logger.info(f"Atomic Reload successfully completed for Camera #{camera_id}")
                return True

            except Exception as e:
                logger.error(f"Error during atomic reload of Camera #{camera_id}: {e}")
                return False

    def remove_camera(self, camera_id: int):
        """카메라 제거 시 커넥션 닫기"""
        if camera_id in self._controllers:
            asyncio.create_task(self._controllers[camera_id].disconnect())
            del self._controllers[camera_id]

camera_manager = CameraManager()
