import pytest
import asyncio
from typing import Optional, Dict
from app.services.ptz.base import PTZControllerBase
from app.services.ptz.guard import ProtectedPTZController

class MockPTZController(PTZControllerBase):
    def __init__(self):
        self.saved_presets = {}
        self.recalled_presets = []
        self.connected = False

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
        return True

    async def zoom_relative(self, zoom_speed: int, zoom_dir: str) -> bool:
        return True

    async def stop(self) -> bool:
        return True

    async def inquire_position(self) -> Optional[Dict[str, int]]:
        return {"pan": 100, "tilt": -50, "zoom": 1200}

    async def move_absolute(self, pan_pos: int, tilt_pos: int, pan_speed: int = 10, tilt_speed: int = 10) -> bool:
        return True


def test_protected_ptz_controller_live_save():
    async def _run():
        mock_ptz = MockPTZController()
        protected_ptz = ProtectedPTZController(mock_ptz, protected_base_presets={1, 2, 3})

        assert await protected_ptz.save_preset(101) is True
        assert await protected_ptz.save_preset(102) is True
        assert 101 in mock_ptz.saved_presets
        assert 102 in mock_ptz.saved_presets

    asyncio.run(_run())


def test_protected_ptz_controller_base_save_blocked():
    async def _run():
        mock_ptz = MockPTZController()
        protected_ptz = ProtectedPTZController(mock_ptz, protected_base_presets={1, 2, 3})

        with pytest.raises(PermissionError) as exc_info:
            await protected_ptz.save_preset(1)
        assert "Attempted to OVERWRITE protected BASE preset #1" in str(exc_info.value)

        with pytest.raises(PermissionError):
            await protected_ptz.save_preset(2)

        with pytest.raises(PermissionError):
            await protected_ptz.save_preset(3)

        assert 1 not in mock_ptz.saved_presets
        assert 2 not in mock_ptz.saved_presets
        assert 3 not in mock_ptz.saved_presets

    asyncio.run(_run())


def test_protected_ptz_controller_update_presets():
    async def _run():
        mock_ptz = MockPTZController()
        protected_ptz = ProtectedPTZController(mock_ptz, protected_base_presets={1})

        protected_ptz.update_protected_presets({1, 4, 5})

        with pytest.raises(PermissionError):
            await protected_ptz.save_preset(4)

        assert await protected_ptz.save_preset(2) is True

    asyncio.run(_run())

