import pytest
import sqlite3
from unittest.mock import MagicMock, AsyncMock, patch
import numpy as np

from app.services.autoset_settings import (
    autoset_settings_service,
    EffectiveAutoSetSettings,
    SYSTEM_HARD_MAX_PAN_DELTA,
    SYSTEM_HARD_MAX_TILT_DELTA
)
from app.services.ptz.motion_controller import MotionController, TargetError
from app.services.autoset_engine import AutoSetEngine
from app.database import get_db_connection

@pytest.mark.unit
def test_field_level_merge_and_overrides(in_memory_db):
    """
    [FIELD-LEVEL MERGE TEST]
    Global: pan_gain=18.0, tilt_gain=14.0, deadzone_x=0.03
    Camera 1: pan_gain=14.0, tilt_gain=NULL, deadzone_x=NULL
    Preset 1 (seeded for Camera 1): pan_gain=NULL, deadzone_x=0.02
    Resolved Effective Settings:
    - pan_gain = 14.0 (Camera Override)
    - tilt_gain = 14.0 (Global Default)
    - deadzone_x = 0.02 (Preset Override)
    """
    # 1. Global 설정 저장
    autoset_settings_service.save_settings(
        scope="GLOBAL", camera_id=None, preset_id=None,
        data={"pan_gain": 18.0, "tilt_gain": 14.0, "deadzone_x": 0.03, "tolerance_x": 0.03}
    )

    # 2. Camera 1 Override 저장
    autoset_settings_service.save_settings(
        scope="CAMERA", camera_id=1, preset_id=None,
        data={"pan_gain": 14.0}
    )

    # 3. Preset 1 Override 저장
    autoset_settings_service.save_settings(
        scope="PRESET", camera_id=1, preset_id=1,
        data={"deadzone_x": 0.02, "tolerance_x": 0.02}
    )

    eff = autoset_settings_service.get_effective_settings(camera_id=1, preset_id=1)

    assert eff.pan_gain == 14.0      # From Camera
    assert eff.tilt_gain == 14.0     # From Global
    assert eff.deadzone_x == 0.02    # From Preset
    assert eff.scope_resolved == "PRESET"


@pytest.mark.unit
def test_override_deletion_and_fallback(in_memory_db):
    """
    Preset Override 삭제 시 Camera/Global 상속 복귀,
    Camera Override 삭제 시 Global 상속 복귀 검증
    """
    autoset_settings_service.save_settings("GLOBAL", None, None, {"pan_gain": 18.0})
    autoset_settings_service.save_settings("CAMERA", 1, None, {"pan_gain": 14.0})
    autoset_settings_service.save_settings("PRESET", 1, 1, {"pan_gain": 10.0})

    # 1. Preset override 존재 시 10.0
    eff1 = autoset_settings_service.get_effective_settings(1, 1)
    assert eff1.pan_gain == 10.0

    # 2. Preset override 삭제 후 -> Camera (14.0) 복귀
    autoset_settings_service.delete_override("PRESET", 1, 1)
    eff2 = autoset_settings_service.get_effective_settings(1, 1)
    assert eff2.pan_gain == 14.0

    # 3. Camera override 삭제 후 -> Global (18.0) 복귀
    autoset_settings_service.delete_override("CAMERA", 1, None)
    eff3 = autoset_settings_service.get_effective_settings(1, 1)
    assert eff3.pan_gain == 18.0


@pytest.mark.unit
def test_preset_camera_hierarchy_validation(in_memory_db):
    """
    [PRESET-CAMERA HIERARCHY VALIDATION]
    타 카메라(Camera #2)에 속한 Preset #1로 PRESET Override 저장을 시도할 때
    ValueError 거부 검증
    """
    with pytest.raises(ValueError) as exc_info:
        # Preset #1은 Camera #1 소속임에도 Camera #2로 저장을 시도함
        autoset_settings_service.save_settings(
            scope="PRESET", camera_id=2, preset_id=1,
            data={"pan_gain": 12.0}
        )
    assert "does not belong to Camera #2" in str(exc_info.value)


@pytest.mark.unit
def test_tolerance_smaller_than_deadzone_rejected(in_memory_db):
    """
    tolerance_x < deadzone_x 인 경우 (무한 수렴 루프 발생 위험)
    Validation 거부 검증
    """
    with pytest.raises(ValueError) as exc_info:
        autoset_settings_service.save_settings(
            scope="GLOBAL", camera_id=None, preset_id=None,
            data={"deadzone_x": 0.05, "tolerance_x": 0.02}
        )
    assert "tolerance_x cannot be smaller than deadzone_x" in str(exc_info.value)


@pytest.mark.unit
def test_axis_independent_deadzone_4_combinations():
    """
    [AXIS-INDEPENDENT DEAD ZONE TEST]
    X/Y 축별 독립적 Dead Zone 처리 4가지 조합 검증:
    1. X IN / Y OUT -> pan_dir = 'stop', tilt_dir != 'stop'
    2. X OUT / Y IN -> pan_dir != 'stop', tilt_dir = 'stop'
    3. X IN / Y IN -> pan_dir = 'stop', tilt_dir = 'stop'
    4. X OUT / Y OUT -> pan_dir != 'stop', tilt_dir != 'stop'
    """
    mock_ptz = MagicMock()
    settings = autoset_settings_service.get_effective_settings()  # deadzone_x=0.03, deadzone_y=0.03
    controller = MotionController(mock_ptz, settings=settings)

    # 1. X IN (0.01) / Y OUT (0.10)
    err1 = TargetError(x_error=0.01, y_error=0.10, scale_error=0.0, confidence=0.9, valid=True)
    _, _, p_dir1, t_dir1, _, _ = controller.calculate_speeds(err1)
    assert p_dir1 == "stop"
    assert t_dir1 == "down"

    # 2. X OUT (0.10) / Y IN (0.01)
    err2 = TargetError(x_error=0.10, y_error=0.01, scale_error=0.0, confidence=0.9, valid=True)
    _, _, p_dir2, t_dir2, _, _ = controller.calculate_speeds(err2)
    assert p_dir2 == "right"
    assert t_dir2 == "stop"

    # 3. X IN (0.01) / Y IN (0.01)
    err3 = TargetError(x_error=0.01, y_error=0.01, scale_error=0.0, confidence=0.9, valid=True)
    _, _, p_dir3, t_dir3, _, _ = controller.calculate_speeds(err3)
    assert p_dir3 == "stop"
    assert t_dir3 == "stop"

    # 4. X OUT (0.10) / Y OUT (0.10)
    err4 = TargetError(x_error=0.10, y_error=0.10, scale_error=0.0, confidence=0.9, valid=True)
    _, _, p_dir4, t_dir4, _, _ = controller.calculate_speeds(err4)
    assert p_dir4 == "right"
    assert t_dir4 == "down"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_system_hard_clamp_enforcement():
    """
    [SYSTEM HARD CLAMP SAFETY TEST]
    DB/UI에서 max_pan_limit = 999.0으로 극단적으로 크게 설정하더라도
    최종 PTZ 이동 클램프는 SYSTEM_HARD_MAX_PAN_DELTA(15.0) 이하로 제어됨을 검증.
    """
    mock_ptz = MagicMock()
    mock_ptz.stop = AsyncMock(return_value=True)
    mock_ptz.move_relative = AsyncMock(return_value=True)

    # DB soft limit = 999.0
    custom_settings = autoset_settings_service.get_effective_settings()
    # frozen dataclass이므로 object.__setattr__ 사용 또는 DB 저장을 거침
    autoset_settings_service.save_settings("GLOBAL", None, None, {"max_pan_limit": 999.0})
    settings = autoset_settings_service.get_effective_settings()

    assert settings.max_pan_limit == 999.0  # DB에는 999.0 저장됨

    controller = MotionController(mock_ptz, settings=settings)

    # 이미 14.5 누적 상태에서 1.0 추가 이동 시도 -> 15.5 > SYSTEM_HARD_MAX_PAN_DELTA(15.0)
    controller.accumulated_pan_step = 14.5
    err = TargetError(x_error=0.5, y_error=0.0, scale_error=0.0, confidence=0.9, valid=True)

    ok = await controller.apply_step_correction(err, pan_limit=999.0, tilt_limit=999.0, zoom_limit=999.0, step_duration=0.01)

    # System Hard Clamp(15.0) 초과로 차단 및 stop() 호출 확인
    assert ok is False
    mock_ptz.stop.assert_called()


@pytest.mark.unit
def test_calculation_test_pure_math():
    """
    [CALCULATION TEST - ZERO RTSP, ZERO AI, ZERO PTZ]
    Calculation Test 수치만으로 Pure Math 계산이 정확히 수행되는지 검증
    """
    engine = AutoSetEngine()
    res = engine.run_calculation_test(
        target_x=0.5, target_y=0.3,
        detected_x=0.6, detected_y=0.4
    )

    assert res["errors"]["x_error"] == 0.1
    assert res["errors"]["y_error"] == 0.1
    assert res["deadzone_status"]["fully_in_deadzone"] is False
    assert "final_hard_clamped_pan" in res["calculated_deltas"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_live_dry_run_skips_ptz_and_preset_save(in_memory_db, monkeypatch):
    """
    [LIVE DRY RUN SAFETY TEST]
    Live Dry Run 실행 시 RTSP 프레임 및 AI 감지는 수행되지만
    PTZ Move ❌, Preset Recall ❌, Preset Save ❌는 절대 호출되지 않음을 검증.
    """
    engine = AutoSetEngine()

    raw_ptz = MagicMock()
    raw_ptz.recall_preset = AsyncMock(return_value=True)
    raw_ptz.save_preset = AsyncMock(return_value=True)
    raw_ptz.move_relative = AsyncMock(return_value=True)

    protected_ptz = ProtectedPTZController(raw_ptz, protected_base_presets={1})
    monkeypatch.setattr("app.services.autoset_engine.camera_manager.get_protected_controller", lambda cid: protected_ptz)

    mock_grabber = MagicMock()
    dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    mock_grabber.get_latest_frame.return_value = (dummy_frame, 1.0, 1)
    mock_grabber.start = MagicMock()
    mock_grabber.stop = MagicMock()
    mock_grabber.flush_buffer = MagicMock()
    monkeypatch.setattr("app.services.autoset_engine.FrameGrabber", lambda url: mock_grabber)

    res = await engine.run_live_dry_run(1)

    assert res["ptz_moved"] is False
    assert res["preset_saved"] is False
    assert "⚠️ Live Dry Run" in res["warning_notice"]

    # PTZ 하드웨어 명령이 100% 안 불렸음을 검증
    raw_ptz.recall_preset.assert_not_called()
    raw_ptz.save_preset.assert_not_called()
    raw_ptz.move_relative.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tolerance_pre_check_avoids_extra_movement(in_memory_db, monkeypatch):
    """
    [TOLERANCE PRE-CHECK SAFETY TEST]
    1차 Iteration에서 이미 Target Tolerance 수렴을 만족한 경우
    PTZ 이동 명령을 1회도 보내지 않고 바로 SUCCESS로 종료하는지 검증.
    """
    # stable_frames = 1
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

    protected_ptz = ProtectedPTZController(raw_ptz, protected_base_presets={1})
    monkeypatch.setattr("app.services.autoset_engine.camera_manager.get_protected_controller", lambda cid: protected_ptz)

    mock_grabber = MagicMock()
    dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    mock_grabber.get_latest_frame.return_value = (dummy_frame, 1.0, 1)
    monkeypatch.setattr("app.services.autoset_engine.FrameGrabber", lambda url: mock_grabber)

    # 오차가 tolerance(0.03) 이내인 수렴 PoseResult
    kps = np.zeros((17, 2), dtype=np.float32)
    kps[1] = [0.495, 0.30]
    kps[2] = [0.505, 0.30]
    converged_pose = MagicMock()
    converged_pose.center_x = 0.50
    converged_pose.center_y = 0.30
    converged_pose.width = 0.2
    converged_pose.height = 0.6
    converged_pose.bbox = [0.4, 0.2, 0.6, 0.8]
    converged_pose.bbox_score = 0.95
    converged_pose.get_keypoint.side_effect = lambda name: [0.50, 0.30, 0.9] if name in ("left_eye", "right_eye") else None

    async def mock_detect_async(frame, roi):
        return [converged_pose]

    monkeypatch.setattr(engine.worker_pool, "detect_async", mock_detect_async)

    result = await engine.run_preset_autoset(1)

    assert result is True
    # 사전 수렴 판정으로 PTZ 이동(move_relative)이 단 1회도 실행되지 않고 바로 LIVE Save됨을 검증
    raw_ptz.move_relative.assert_not_called()
    raw_ptz.save_preset.assert_called_with(101)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stalled_early_termination(in_memory_db, monkeypatch):
    """
    [STALLED EARLY TERMINATION TEST]
    Tolerance는 미충족했지만 DeadZone/MinCorrection으로 인해 PTZ Delta가 0이 된 경우
    무한 루프를 돌지 않고 STALLED 처리로 즉시 조기 종료하는지 검증.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE presets SET stable_frames = 1 WHERE id = 1")
    conn.commit()
    conn.close()

    # Tolerance = 0.05, DeadZone = 0.03
    autoset_settings_service.save_settings("GLOBAL", None, None, {"deadzone_x": 0.03, "tolerance_x": 0.05})

    engine = AutoSetEngine()

    raw_ptz = MagicMock()
    raw_ptz.recall_preset = AsyncMock(return_value=True)
    raw_ptz.save_preset = AsyncMock(return_value=True)
    raw_ptz.move_relative = AsyncMock(return_value=True)

    protected_ptz = ProtectedPTZController(raw_ptz, protected_base_presets={1})
    monkeypatch.setattr("app.services.autoset_engine.camera_manager.get_protected_controller", lambda cid: protected_ptz)

    mock_grabber = MagicMock()
    dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    mock_grabber.get_latest_frame.return_value = (dummy_frame, 1.0, 1)
    monkeypatch.setattr("app.services.autoset_engine.FrameGrabber", lambda url: mock_grabber)

    # 오차 0.02 (DeadZone 0.03 이내이므로 delta = 0, 그러나 Tolerance 0.01에는 못 미침)
    autoset_settings_service.save_settings("GLOBAL", None, None, {"deadzone_x": 0.03, "tolerance_x": 0.05})

    # Deadzone 이내 오차 생성
    stalled_pose = MagicMock()
    stalled_pose.center_x = 0.52 # error = 0.02 <= deadzone 0.03
    stalled_pose.center_y = 0.30
    stalled_pose.width = 0.2
    stalled_pose.height = 0.6
    stalled_pose.bbox = [0.42, 0.2, 0.62, 0.8]
    stalled_pose.bbox_score = 0.95
    stalled_pose.get_keypoint.side_effect = lambda name: [0.52, 0.30, 0.9] if name in ("left_eye", "right_eye") else None

    async def mock_detect_async(frame, roi):
        return [stalled_pose]

    monkeypatch.setattr(engine.worker_pool, "detect_async", mock_detect_async)

    # Tolerance를 0.01로 재설정하여 error 0.02가 tolerance 밖이 되도록 함
    # (validation 허용을 위해 deadzone도 0.01로 임시 지정)
    autoset_settings_service.save_settings("GLOBAL", None, None, {"deadzone_x": 0.03, "tolerance_x": 0.03})

    result = await engine.run_preset_autoset(1)

    # STALLED 조기 종료로 False 반환 및 LIVE Save 미실행 확인
    assert result is False
    raw_ptz.save_preset.assert_not_called()
