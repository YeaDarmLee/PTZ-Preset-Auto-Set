import pytest
import sqlite3
import numpy as np
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Optional, Dict, Any, List

from app.services.ptz.base import PTZControllerBase
from app.services.ptz.guard import ProtectedPTZController
from app.database import init_db

class MockPTZController(PTZControllerBase):
    """단위 테스트용 Mock PTZ Controller"""
    def __init__(self):
        self.saved_presets: Dict[int, bool] = {}
        self.recalled_presets: List[int] = []
        self.connected = False
        self.positions = {"pan": 100, "tilt": -50, "zoom": 1200}
        self.movement_history = []

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def disconnect(self) -> None:
        self.connected = False

    async def recall_preset(self, preset_no: int) -> bool:
        self.recalled_presets.append(preset_no)
        return True

    async def save_preset(self, preset_no: int) -> bool:
        self.saved_presets[preset_no] = True
        return True

    async def move_relative(self, pan_speed: int, tilt_speed: int, pan_dir: str, tilt_dir: str) -> bool:
        self.movement_history.append(("move_relative", pan_speed, tilt_speed, pan_dir, tilt_dir))
        return True

    async def zoom_relative(self, zoom_speed: int, zoom_dir: str) -> bool:
        self.movement_history.append(("zoom_relative", zoom_speed, zoom_dir))
        return True

    async def stop(self) -> bool:
        self.movement_history.append(("stop",))
        return True

    async def inquire_position(self) -> Optional[Dict[str, int]]:
        return self.positions

    async def move_absolute(self, pan_pos: int, tilt_pos: int, pan_speed: int = 10, tilt_speed: int = 10) -> bool:
        self.movement_history.append(("move_absolute", pan_pos, tilt_pos, pan_speed, tilt_speed))
        return True


@pytest.fixture
def mock_raw_ptz():
    return MockPTZController()


@pytest.fixture
def protected_ptz(mock_raw_ptz):
    return ProtectedPTZController(mock_raw_ptz, protected_base_presets={1, 2, 3})


@pytest.fixture(autouse=True)
def in_memory_db(monkeypatch):
    """In-memory SQLite DB 공유 인스턴스를 모든 DB 관련 테스트에 자동 패치"""
    db_uri = "file:test_autoset_db?mode=memory&cache=shared"
    
    # DB 테이블 및 시드 데이터 초기화
    def _get_test_db_conn():
        conn = sqlite3.connect(db_uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    # 기존 get_db_connection을 in-memory DB 연결로 패치
    monkeypatch.setattr("app.database.get_db_connection", _get_test_db_conn)
    monkeypatch.setattr("app.services.autoset_engine.get_db_connection", _get_test_db_conn)
    monkeypatch.setattr("app.services.camera_manager.get_db_connection", _get_test_db_conn)

    conn = _get_test_db_conn()
    cursor = conn.cursor()
    # 테이블 리셋 후 재초기화
    cursor.execute("DROP TABLE IF EXISTS autoset_logs")
    cursor.execute("DROP TABLE IF EXISTS presets")
    cursor.execute("DROP TABLE IF EXISTS cameras")
    cursor.execute("DROP TABLE IF EXISTS system_settings")
    conn.commit()
    conn.close()

    init_db()
    yield _get_test_db_conn


@pytest.fixture
def sample_frame():
    """테스트용 가상 BGR 이미지 프레임 (1920x1080)"""
    return np.zeros((1080, 1920, 3), dtype=np.uint8)
