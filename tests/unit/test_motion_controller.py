import pytest
from unittest.mock import MagicMock, AsyncMock
from app.services.ptz.motion_controller import MotionController, TargetError

@pytest.mark.unit
def test_calculate_speeds_right_down_wide():
    """
    x_error > 0 (오른쪽 이동), y_error > 0 (아래 이동), scale_error > 0 (줌아웃)
    속도 계산 및 방향 매핑 검증
    """
    mock_ptz = MagicMock()
    controller = MotionController(mock_ptz, p_gain_pan=20.0, p_gain_tilt=10.0, p_gain_zoom=5.0)

    error = TargetError(
        x_error=0.20,
        y_error=0.30,
        scale_error=0.40,
        confidence=0.9,
        valid=True
    )

    pan_spd, tilt_spd, pan_dir, tilt_dir, zoom_spd, zoom_dir = controller.calculate_speeds(error)

    assert pan_dir == "right"
    assert pan_spd == 4  # 0.20 * 20.0 = 4
    assert tilt_dir == "down"
    assert tilt_spd == 3  # 0.30 * 10.0 = 3
    assert zoom_dir == "wide"
    assert zoom_spd == 2  # 0.40 * 5.0 = 2


@pytest.mark.unit
def test_calculate_speeds_left_up_tele():
    """
    x_error < 0 (왼쪽 이동), y_error < 0 (위 이동), scale_error < 0 (줌인)
    속도 계산 및 방향 매핑 검증
    """
    mock_ptz = MagicMock()
    controller = MotionController(mock_ptz, p_gain_pan=20.0, p_gain_tilt=10.0, p_gain_zoom=5.0)

    error = TargetError(
        x_error=-0.15,
        y_error=-0.25,
        scale_error=-0.35,
        confidence=0.9,
        valid=True
    )

    pan_spd, tilt_spd, pan_dir, tilt_dir, zoom_spd, zoom_dir = controller.calculate_speeds(error)

    assert pan_dir == "left"
    assert pan_spd == 3  # abs(-0.15) * 20.0 = 3
    assert tilt_dir == "up"
    assert tilt_spd == 2  # abs(-0.25) * 10.0 = 2
    assert zoom_dir == "tele"
    assert zoom_spd == 1  # abs(-0.35) * 5.0 = 1.75 -> int 1


@pytest.mark.unit
def test_calculate_speeds_target_center_stop():
    """정확히 Center (x_error=0, y_error=0, scale_error=0)인 경우 stop 판정"""
    mock_ptz = MagicMock()
    controller = MotionController(mock_ptz)

    error = TargetError(x_error=0.0, y_error=0.0, scale_error=0.0, confidence=1.0, valid=True)
    pan_spd, tilt_spd, pan_dir, tilt_dir, zoom_spd, zoom_dir = controller.calculate_speeds(error)

    assert pan_dir == "stop"
    assert pan_spd == 0
    assert tilt_dir == "stop"
    assert tilt_spd == 0
    assert zoom_dir == "stop"
    assert zoom_spd == 0


@pytest.mark.unit
def test_calculate_speeds_clamp_limits():
    """속도값이 최대 상한선(Pan 24, Tilt 20, Zoom 7)을 초과할 때 Clamp 제어 검증"""
    mock_ptz = MagicMock()
    controller = MotionController(mock_ptz, p_gain_pan=1000.0, p_gain_tilt=1000.0, p_gain_zoom=1000.0)

    error = TargetError(x_error=1.0, y_error=1.0, scale_error=1.0, confidence=1.0, valid=True)
    pan_spd, tilt_spd, pan_dir, tilt_dir, zoom_spd, zoom_dir = controller.calculate_speeds(error)

    assert pan_spd == 24
    assert tilt_spd == 20
    assert zoom_spd == 7


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_step_correction_safety_limit_exceeded():
    """
    [SAFETY LIMIT EXCEEDED TEST]
    누적 이동량이 안전 한계(pan_limit, tilt_limit, zoom_limit)를 초과할 경우 
    이동을 차단(False 반환)하고 ptz.stop()을 호출하는지 검증.
    """
    mock_ptz = MagicMock()
    mock_ptz.stop = AsyncMock(return_value=True)
    mock_ptz.move_relative = AsyncMock(return_value=True)

    controller = MotionController(mock_ptz, p_gain_pan=100.0)
    controller.accumulated_pan_step = 4.9  # pan_limit = 5.0 에 임계 접근

    error = TargetError(x_error=0.5, y_error=0.0, scale_error=0.0, confidence=0.9, valid=True)

    # 추가 이동량이 pan_limit(5.0)을 초과하도록 설정
    ok = await controller.apply_step_correction(
        error=error,
        pan_limit=5.0,
        tilt_limit=5.0,
        zoom_limit=10.0,
        step_duration=0.01
    )

    assert ok is False
    # stop() 이 차단 후 즉시 호출되었음을 검증
    mock_ptz.stop.assert_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_step_correction_low_confidence_rejected():
    """신뢰도가 낮은(confidence < 0.3) TargetError는 이동 적용 거부 검증"""
    mock_ptz = MagicMock()
    mock_ptz.move_relative = AsyncMock(return_value=True)

    controller = MotionController(mock_ptz)
    error = TargetError(x_error=0.5, y_error=0.0, scale_error=0.0, confidence=0.2, valid=True)

    ok = await controller.apply_step_correction(error=error, pan_limit=5.0, tilt_limit=5.0, zoom_limit=5.0)

    assert ok is False
    mock_ptz.move_relative.assert_not_called()
