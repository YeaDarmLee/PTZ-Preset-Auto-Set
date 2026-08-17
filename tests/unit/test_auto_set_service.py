import pytest
import asyncio
import numpy as np
from unittest.mock import MagicMock, AsyncMock
from app.services.autoset_engine import AutoSetEngine
from app.services.vision.base_detector import PoseResult
from app.services.ptz.guard import ProtectedPTZController
from app.database import get_db_connection

@pytest.fixture
def mock_pose_result_converged():
    """Target X=0.5, Y=0.3에 거의 수렴한 인물 PoseResult"""
    kps = np.zeros((17, 2), dtype=np.float32)
    kps[1] = [0.49, 0.30]  # left eye
    kps[2] = [0.51, 0.30]  # right eye
    scores = np.ones(17, dtype=np.float32)

    return PoseResult(
        bbox=[0.4, 0.2, 0.6, 0.8],  # height = 0.6
        bbox_score=0.9,
        keypoints=kps,
        keypoint_scores=scores
    )

@pytest.mark.unit
@pytest.mark.asyncio
async def test_auto_set_normal_success_flow(in_memory_db, mock_pose_result_converged, monkeypatch):
    """
    [AUTO SET NORMAL SUCCESS TEST]
    모든 단계(BASE recall -> RTSP Frame -> Pose 감지 -> Target 수렴 -> LIVE Save)가
    성공할 때 최종 상태가 True 및 SUCCESS가 되는지 검증.
    """
    # 빠르게 수렴하도록 stable_frames = 1 설정
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE presets SET stable_frames = 1 WHERE id = 1")
    conn.commit()
    conn.close()

    engine = AutoSetEngine()

    raw_ptz = MagicMock()
    raw_ptz.recall_preset = AsyncMock(return_value=True)
    raw_ptz.save_preset = AsyncMock(return_value=True)
    raw_ptz.move_relative = AsyncMock(return_value=True)
    raw_ptz.zoom_relative = AsyncMock(return_value=True)
    raw_ptz.stop = AsyncMock(return_value=True)

    protected_ptz = ProtectedPTZController(raw_ptz, protected_base_presets={1})
    monkeypatch.setattr("app.services.autoset_engine.camera_manager.get_protected_controller", lambda cam_id: protected_ptz)

    mock_grabber = MagicMock()
    dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    mock_grabber.get_latest_frame.return_value = (dummy_frame, 1.0, 1)
    mock_grabber.start = MagicMock()
    mock_grabber.stop = MagicMock()
    mock_grabber.flush_buffer = MagicMock()
    monkeypatch.setattr("app.services.autoset_engine.FrameGrabber", lambda url: mock_grabber)

    async def mock_detect_async(frame, roi):
        return [mock_pose_result_converged]

    monkeypatch.setattr(engine.worker_pool, "detect_async", mock_detect_async)

    result = await engine.run_preset_autoset(1)

    assert result is True
    raw_ptz.recall_preset.assert_called_with(1)
    raw_ptz.save_preset.assert_called_with(101)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_auto_set_no_person_detected_flow(in_memory_db, monkeypatch):
    """
    [AUTO SET NO PERSON DETECTED TEST]
    인물이 미검출(0명)된 경우 PTZ 이동 명령이 실행되지 않고 LIVE Preset 저장이 스킵되며 FAILED 반환.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE presets SET stable_frames = 1 WHERE id = 1")
    conn.commit()
    conn.close()

    engine = AutoSetEngine()

    raw_ptz = MagicMock()
    raw_ptz.recall_preset = AsyncMock(return_value=True)
    raw_ptz.save_preset = AsyncMock(return_value=True)
    raw_ptz.move_relative = AsyncMock(return_value=True)
    raw_ptz.stop = AsyncMock(return_value=True)

    protected_ptz = ProtectedPTZController(raw_ptz, protected_base_presets={1})
    monkeypatch.setattr("app.services.autoset_engine.camera_manager.get_protected_controller", lambda cam_id: protected_ptz)

    mock_grabber = MagicMock()
    dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    mock_grabber.get_latest_frame.return_value = (dummy_frame, 1.0, 1)
    monkeypatch.setattr("app.services.autoset_engine.FrameGrabber", lambda url: mock_grabber)

    async def mock_detect_empty(frame, roi):
        return []

    monkeypatch.setattr(engine.worker_pool, "detect_async", mock_detect_empty)

    result = await engine.run_preset_autoset(1)

    assert result is False
    raw_ptz.save_preset.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_auto_set_rtsp_frame_grab_failure_flow(in_memory_db, monkeypatch):
    """
    [AUTO SET RTSP FRAME FAIL TEST]
    RTSP 스트림 프레임 읽기 실패(None) 시 AI 추론 및 PTZ 이동/저장이 모두 스킵되고 FAILED 처리.
    """
    engine = AutoSetEngine()

    raw_ptz = MagicMock()
    raw_ptz.recall_preset = AsyncMock(return_value=True)
    raw_ptz.save_preset = AsyncMock(return_value=True)

    protected_ptz = ProtectedPTZController(raw_ptz, protected_base_presets={1})
    monkeypatch.setattr("app.services.autoset_engine.camera_manager.get_protected_controller", lambda cid: protected_ptz)

    mock_grabber = MagicMock()
    mock_grabber.get_latest_frame.return_value = (None, 0.0, 0)
    monkeypatch.setattr("app.services.autoset_engine.FrameGrabber", lambda url: mock_grabber)

    result = await engine.run_preset_autoset(1)

    assert result is False
    raw_ptz.save_preset.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_auto_set_live_save_failure_flow(in_memory_db, mock_pose_result_converged, monkeypatch):
    """
    [AUTO SET LIVE SAVE FAIL TEST]
    Target 보정까지 수렴에 성공했으나 LIVE Preset save 명령 시점에서 Exception이 발생할 경우
    전체 결과가 SUCCESS가 아닌 FAILED로 처리되는지 검증.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE presets SET stable_frames = 1 WHERE id = 1")
    conn.commit()
    conn.close()

    engine = AutoSetEngine()

    raw_ptz = MagicMock()
    raw_ptz.recall_preset = AsyncMock(return_value=True)
    raw_ptz.save_preset = AsyncMock(side_effect=RuntimeError("VISCA Save Timeout"))

    protected_ptz = ProtectedPTZController(raw_ptz, protected_base_presets={1})
    monkeypatch.setattr("app.services.autoset_engine.camera_manager.get_protected_controller", lambda cid: protected_ptz)

    mock_grabber = MagicMock()
    dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    mock_grabber.get_latest_frame.return_value = (dummy_frame, 1.0, 1)
    monkeypatch.setattr("app.services.autoset_engine.FrameGrabber", lambda url: mock_grabber)

    async def mock_detect_async(frame, roi):
        return [mock_pose_result_converged]

    monkeypatch.setattr(engine.worker_pool, "detect_async", mock_detect_async)

    result = await engine.run_preset_autoset(1)
    assert result is False
