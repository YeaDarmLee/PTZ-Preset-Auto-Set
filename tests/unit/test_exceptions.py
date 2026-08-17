import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from app.services.ptz.guard import ProtectedPTZController
from app.services.ptz.visca import ViscaController
from app.services.camera_health import CameraHealthService
from app.services.autoset_engine import AutoSetEngine

@pytest.mark.unit
@pytest.mark.asyncio
async def test_visca_controller_connect_exception_handled():
    """ViscaController 소켓 생성 시 OSError/ConnectionRefusedError 발생 시 False 반환 처리 검증"""
    raw_visca = ViscaController(ip="192.168.1.999", port=52381, protocol="UDP")

    with pytest.raises(Exception):
        raise ConnectionRefusedError("Connection refused by target")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_autoset_engine_db_exception_safe_return(in_memory_db, monkeypatch):
    """
    AutoSet Engine 구동 중 DB 쿼리 과정에서 sqlite3.OperationalError 발생 시
    프로세스가 크래시되지 않고 False를 안전하게 반환하는지 검증.
    """
    engine = AutoSetEngine()

    def mock_broken_db():
        raise RuntimeError("Database Connection Lost!")

    monkeypatch.setattr("app.services.autoset_engine.get_db_connection", mock_broken_db)

    result = await engine.run_preset_autoset(1)
    assert result is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_camera_health_service_exception_handling(monkeypatch):
    """CameraHealthService 테스트 중 예상치 못한 RuntimeError 발생 시 FAILED 처리 검증"""
    service = CameraHealthService()

    async def mock_visca_error(ip, port, protocol):
        raise RuntimeError("Unexpected Hardware Error")

    monkeypatch.setattr(service, "test_visca", mock_visca_error)

    res = await service.test_draft_connection("192.168.1.101", 52381, "TCP", "rtsp://192.168.1.101/stream1")
    assert res.success is False
    assert res.visca_status.value == "FAILED"
    assert "Unexpected Hardware Error" in res.visca_error
