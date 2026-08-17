import logging
from typing import Set, Optional, Dict
from app.services.ptz.base import PTZControllerBase

logger = logging.getLogger(__name__)

class ProtectedPTZController(PTZControllerBase):
    """
    [DOUBLE SAFETY HARD GUARD]
    기본 PTZController(예: ViscaController)를 감싸서
    등록된 BASE Preset 번호에 대한 SAVE (메모리 덮어쓰기) 명령을 
    코드 레벨에서 차단하는 안전 보호 래퍼 클래스.
    """

    def __init__(self, raw_controller: PTZControllerBase, protected_base_presets: Optional[Set[int]] = None):
        self._controller = raw_controller
        self._protected_presets: Set[int] = set(protected_base_presets) if protected_base_presets else set()

    def update_protected_presets(self, protected_base_presets: Set[int]) -> None:
        """보호할 BASE Preset 번호 목록 업데이트"""
        self._protected_presets = set(protected_base_presets)
        logger.info(f"Updated protected BASE presets: {self._protected_presets}")

    def get_protected_presets(self) -> Set[int]:
        return set(self._protected_presets)

    async def save_preset(self, preset_no: int) -> bool:
        """
        프리셋 저장 명령 Intercept
        🚨 덮어쓰기 시도가 BASE Preset 번호에 해당할 경우 하드웨어 명령을 송신하지 않고 PermissionError 발생
        """
        if preset_no in self._protected_presets:
            error_msg = (
                f"[CRITICAL SAFETY HARD GUARD] Attempted to OVERWRITE protected BASE preset #{preset_no}! "
                f"Operation blocked immediately."
            )
            logger.critical(error_msg)
            raise PermissionError(error_msg)

        logger.info(f"Saving LIVE preset #{preset_no} via ProtectedPTZController")
        return await self._controller.save_preset(preset_no)

    async def connect(self) -> bool:
        return await self._controller.connect()

    async def disconnect(self) -> None:
        await self._controller.disconnect()

    async def recall_preset(self, preset_no: int) -> bool:
        logger.info(f"Recalling preset #{preset_no}")
        return await self._controller.recall_preset(preset_no)

    async def move_relative(self, pan_speed: int, tilt_speed: int, pan_dir: str, tilt_dir: str) -> bool:
        return await self._controller.move_relative(pan_speed, tilt_speed, pan_dir, tilt_dir)

    async def zoom_relative(self, zoom_speed: int, zoom_dir: str) -> bool:
        return await self._controller.zoom_relative(zoom_speed, zoom_dir)

    async def stop(self) -> bool:
        return await self._controller.stop()

    async def inquire_position(self) -> Optional[Dict[str, int]]:
        return await self._controller.inquire_position()

    async def move_absolute(self, pan_pos: int, tilt_pos: int, pan_speed: int = 10, tilt_speed: int = 10) -> bool:
        return await self._controller.move_absolute(pan_pos, tilt_pos, pan_speed, tilt_speed)
