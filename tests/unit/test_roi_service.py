import pytest
import numpy as np
from app.services.vision.rtmlib_detector import RTMLibPoseDetector
from app.services.vision.target_calculator import TargetCalculator, VerticalMetric, ScaleMetric
from app.services.vision.stabilizer import TargetMetrics

@pytest.mark.unit
def test_invalid_roi_crop_handling():
    """
    잘못된 ROI 좌표 (x1 > x2 또는 y1 > y2, 너비/높이 <= 0)가 입력되었을 때
    RTMLibPoseDetector.detect가 오류를 던지지 않고 빈 배열 []을 안전하게 반환하는지 검증.
    """
    detector = RTMLibPoseDetector()
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    # 1. Reverse X (x1 > x2)
    res_rev_x = detector.detect(frame, roi=(0.8, 0.1, 0.2, 0.9))
    assert res_rev_x == []

    # 2. Reverse Y (y1 > y2)
    res_rev_y = detector.detect(frame, roi=(0.1, 0.8, 0.9, 0.2))
    assert res_rev_y == []

    # 3. Zero Width (x1 == x2)
    res_zero_w = detector.detect(frame, roi=(0.5, 0.1, 0.5, 0.9))
    assert res_zero_w == []

    # 4. None Frame
    res_none = detector.detect(None, roi=(0.0, 0.0, 1.0, 1.0))
    assert res_none == []


@pytest.mark.unit
def test_target_calculator_error_computation():
    """
    TargetCalculator가 Target (0.50, 0.30, 0.60) 기준에 맞춰
    TargetMetrics로부터 오차(x_error, y_error, scale_error)를 일관되게 반환하는지 검증.
    """
    calculator = TargetCalculator(
        target_x=0.50,
        target_y=0.30,
        target_scale=0.60,
        vertical_metric=VerticalMetric.EYE_Y,
        scale_metric=ScaleMetric.PERSON_HEIGHT
    )

    metrics = TargetMetrics(
        center_x=0.70,     # +0.20 오차
        vertical_val=0.50, # +0.20 오차
        scale_val=0.60,    # 0.0 오차
        confidence=0.95
    )

    err = calculator.calculate_error(metrics)

    assert pytest.approx(err.x_error, 0.001) == 0.20
    assert pytest.approx(err.y_error, 0.001) == 0.20
    assert pytest.approx(err.scale_error, 0.001) == 0.00
    assert err.valid is True


@pytest.mark.unit
def test_target_calculator_null_metrics_handling():
    """TargetMetrics가 None인 경우 valid=False 인 TargetError 반환 확인"""
    calculator = TargetCalculator()
    err = calculator.calculate_error(None)

    assert err.valid is False
    assert err.error_reason == "No stable target metrics"
