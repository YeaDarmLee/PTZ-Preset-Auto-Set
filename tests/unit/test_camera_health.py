import pytest
import asyncio
import numpy as np
from unittest.mock import MagicMock, AsyncMock
from app.services.camera_health import CameraHealthService
from app.services.state_manager import HealthStatus

@pytest.mark.unit
@pytest.mark.asyncio
async def test_visca_tcp_connect_success(monkeypatch):
    """VISCA TCP 연결 성공 시 CONNECTED 및 레이턴시 반환 검증"""
    service = CameraHealthService(visca_timeout_sec=0.1)

    async def mock_open_conn(ip, port):
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock(return_value=None)
        reader = MagicMock()
        return reader, writer

    monkeypatch.setattr("asyncio.open_connection", mock_open_conn)

    status, latency, err = await service.test_visca("192.168.1.101", 52381, "TCP")

    assert status == HealthStatus.CONNECTED
    assert latency is not None
    assert err is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_visca_tcp_connect_timeout(monkeypatch):
    """VISCA TCP 연결 타임아웃 시 FAILED 상태 및 에러 메시지 반환 검증"""
    service = CameraHealthService(visca_timeout_sec=0.01)

    async def mock_open_conn_timeout(ip, port):
        raise asyncio.TimeoutError()

    monkeypatch.setattr("asyncio.open_connection", mock_open_conn_timeout)

    status, latency, err = await service.test_visca("192.168.1.101", 52381, "TCP")

    assert status == HealthStatus.FAILED
    assert latency is None
    assert "Timeout" in err


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rtsp_stream_and_frame_success(monkeypatch):
    """RTSP 오픈 및 1-Frame 수신 성공 시 STREAMING(CONNECTED) 및 해상도 1920x1080 반환 검증"""
    service = CameraHealthService(rtsp_open_timeout_sec=0.5, rtsp_frame_timeout_sec=0.5)

    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    mock_cap.read.return_value = (True, dummy_frame)
    mock_cap.release = MagicMock()

    monkeypatch.setattr("cv2.VideoCapture", lambda url, backend: mock_cap)

    status, resolution, err = await service.test_rtsp("rtsp://192.168.1.101:554/stream1")

    assert status == HealthStatus.CONNECTED
    assert resolution == "1920x1080"
    assert err is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rtsp_stream_open_failed(monkeypatch):
    """RTSP 연결 실패(isOpened=False) 시 FAILED 반환 검증"""
    service = CameraHealthService(rtsp_open_timeout_sec=0.5)

    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = False
    mock_cap.release = MagicMock()

    monkeypatch.setattr("cv2.VideoCapture", lambda url, backend: mock_cap)

    status, resolution, err = await service.test_rtsp("rtsp://192.168.1.101:554/stream1")

    assert status == HealthStatus.FAILED
    assert resolution is None
    assert "Failed to open RTSP stream" in err


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rtsp_frame_grab_failed(monkeypatch):
    """RTSP 오픈 성공했으나 프레임 읽기(read) 실패 시 FAILED 반환 검증"""
    service = CameraHealthService(rtsp_open_timeout_sec=0.5)

    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (False, None)
    mock_cap.release = MagicMock()

    monkeypatch.setattr("cv2.VideoCapture", lambda url, backend: mock_cap)

    status, resolution, err = await service.test_rtsp("rtsp://192.168.1.101:554/stream1")

    assert status == HealthStatus.FAILED
    assert resolution is None
    assert "Failed to grab frame" in err


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ptz_and_video_independence(monkeypatch):
    """
    [INDEPENDENCE TEST]
    PTZ 헬스 상태와 VIDEO 헬스 상태가 상호 독립적으로 판정되는지 검증:
    Case 1: PTZ = CONNECTED, VIDEO = FAILED -> PTZ는 CONNECTED 상태 유지, VIDEO만 FAILED
    Case 2: PTZ = FAILED, VIDEO = CONNECTED -> VIDEO는 CONNECTED 상태 유지, PTZ만 FAILED
    """
    service = CameraHealthService()

    async def mock_visca_ok(ip, port, protocol):
        return HealthStatus.CONNECTED, 5.0, None

    async def mock_rtsp_fail(url):
        return HealthStatus.FAILED, None, "RTSP Error"

    monkeypatch.setattr(service, "test_visca", mock_visca_ok)
    monkeypatch.setattr(service, "test_rtsp", mock_rtsp_fail)

    res1 = await service.test_draft_connection("192.168.1.101", 52381, "TCP", "rtsp://192.168.1.101/stream1")

    assert res1.success is False
    assert res1.visca_status == HealthStatus.CONNECTED
    assert res1.rtsp_status == HealthStatus.FAILED

    async def mock_visca_fail(ip, port, protocol):
        return HealthStatus.FAILED, None, "VISCA Timeout"

    async def mock_rtsp_ok(url):
        return HealthStatus.CONNECTED, "1920x1080", None

    monkeypatch.setattr(service, "test_visca", mock_visca_fail)
    monkeypatch.setattr(service, "test_rtsp", mock_rtsp_ok)

    res2 = await service.test_draft_connection("192.168.1.101", 52381, "TCP", "rtsp://192.168.1.101/stream1")

    assert res2.success is False
    assert res2.visca_status == HealthStatus.FAILED
    assert res2.rtsp_status == HealthStatus.CONNECTED
