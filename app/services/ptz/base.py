from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class PTZControllerBase(ABC):
    """
    PTZ 카메라 제어를 위한 추상 베이스 클래스 (Abstract Base Class)
    """

    @abstractmethod
    async def connect(self) -> bool:
        """카메라 네트워크 연결 설정"""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """카메라 네트워크 연결 해제"""
        pass

    @abstractmethod
    async def recall_preset(self, preset_no: int) -> bool:
        """지정한 프리셋 번호로 카메라 이동"""
        pass

    @abstractmethod
    async def save_preset(self, preset_no: int) -> bool:
        """현재 카메라 위치를 지정한 프리셋 번호에 저장 (하드웨어 메모리 쓰기)"""
        pass

    @abstractmethod
    async def move_relative(self, pan_speed: int, tilt_speed: int, pan_dir: str, tilt_dir: str) -> bool:
        """
        상대적 수동 구동 (Drive)
        pan_dir: 'left', 'right', 'stop'
        tilt_dir: 'up', 'down', 'stop'
        pan_speed / tilt_speed: 1 ~ 24
        """
        pass

    @abstractmethod
    async def zoom_relative(self, zoom_speed: int, zoom_dir: str) -> bool:
        """
        상대적 Zoom 구동
        zoom_dir: 'tele', 'wide', 'stop'
        zoom_speed: 0 ~ 7
        """
        pass

    @abstractmethod
    async def stop(self) -> bool:
        """모든 PTZ 및 Zoom 구동 즉시 정지"""
        pass

    @abstractmethod
    async def inquire_position(self) -> Optional[Dict[str, int]]:
        """
        현재 카메라 위치(Pan, Tilt, Zoom) 레지스터 값 문의
        Returns:
            {"pan": int, "tilt": int, "zoom": int} 또는 None (지원하지 않는 경우)
        """
        pass

    @abstractmethod
    async def move_absolute(self, pan_pos: int, tilt_pos: int, pan_speed: int = 10, tilt_speed: int = 10) -> bool:
        """
        절대 위치 이동
        Returns:
            성공 여부 (미지원시 False)
        """
        pass
