import logging
import math
from dataclasses import dataclass
from typing import Optional, Tuple
from app.services.ptz.guard import ProtectedPTZController

logger = logging.getLogger(__name__)

@dataclass
class TargetError:
    """TargetCalculator가 반환하는 구도 오차 구조체"""
    x_error: float          # Normalized Center X 오차 (-1.0 ~ 1.0)
    y_error: float          # Vertical Metric 오차 (-1.0 ~ 1.0)
    scale_error: float      # Scale Metric 비율 오차 (-1.0 ~ 1.0)
    confidence: float       # Pose Detection 신뢰도 (0.0 ~ 1.0)
    valid: bool             # 유효 여부
    error_reason: Optional[str] = None

class MotionController:
    """
    TargetError(X, Y, Scale 오차)를 해석하여 P-Control(비례 제어) 기반 
    PTZ 구동 속도 및 방향을 계산하고, Safety Limit 내에서 조율하는 컨트롤러
    """

    def __init__(self, ptz: ProtectedPTZController, p_gain_pan: float = 18.0, p_gain_tilt: float = 14.0, p_gain_zoom: float = 5.0):
        self.ptz = ptz
        self.p_gain_pan = p_gain_pan
        self.p_gain_tilt = p_gain_tilt
        self.p_gain_zoom = p_gain_zoom

        # 누적 이동량 기록 (Limit 검사용)
        self.accumulated_pan_step = 0.0
        self.accumulated_tilt_step = 0.0
        self.accumulated_zoom_step = 0.0

    def reset_accumulated_limits(self):
        """AutoSet 1개 프리셋 보정 시작 전 누적 보정량 초기화"""
        self.accumulated_pan_step = 0.0
        self.accumulated_tilt_step = 0.0
        self.accumulated_zoom_step = 0.0

    def calculate_speeds(self, error: TargetError) -> Tuple[int, int, str, str, int, str]:
        """
        TargetError 오차를 바탕으로 Pan/Tilt/Zoom 속도 및 방향 계산
        Returns:
            (pan_speed, tilt_speed, pan_dir, tilt_dir, zoom_speed, zoom_dir)
        """
        # Pan 방향 및 속도 (X error)
        # x_error > 0 인 경우 피사체가 오른쪽 -> 카메라는 오른쪽(right) 이동
        pan_dir = "right" if error.x_error > 0 else ("left" if error.x_error < 0 else "stop")
        raw_pan_speed = int(abs(error.x_error) * self.p_gain_pan)
        pan_speed = max(1, min(24, raw_pan_speed)) if pan_dir != "stop" else 0

        # Tilt 방향 및 속도 (Y error)
        # y_error > 0 인 경우 피사체가 아래 -> 카메라는 아래(down) 이동
        tilt_dir = "down" if error.y_error > 0 else ("up" if error.y_error < 0 else "stop")
        raw_tilt_speed = int(abs(error.y_error) * self.p_gain_tilt)
        tilt_speed = max(1, min(20, raw_tilt_speed)) if tilt_dir != "stop" else 0

        # Zoom 방향 및 속도 (Scale error)
        # scale_error > 0 인 경우 피사체가 너무 큼 -> 카메라는 줌아웃(wide) 이동
        zoom_dir = "wide" if error.scale_error > 0 else ("tele" if error.scale_error < 0 else "stop")
        raw_zoom_speed = int(abs(error.scale_error) * self.p_gain_zoom)
        zoom_speed = max(1, min(7, raw_zoom_speed)) if zoom_dir != "stop" else 0

        return pan_speed, tilt_speed, pan_dir, tilt_dir, zoom_speed, zoom_dir

    async def apply_step_correction(
        self,
        error: TargetError,
        pan_limit: float,
        tilt_limit: float,
        zoom_limit: float,
        step_duration: float = 0.15
    ) -> bool:
        """
        단일 Closed-loop 단계에서의 미세 보정 수행
        Limit 범위를 초과할 경우 False 반환 (AutoSet FAILED 처리 사유)
        """
        if not error.valid or error.confidence < 0.3:
            logger.warning(f"Motion step skipped due to invalid/low confidence error: {error}")
            return False

        pan_spd, tilt_spd, pan_dir, tilt_dir, zoom_spd, zoom_dir = self.calculate_speeds(error)

        # 누적 이동 보정량 가상 업데이트 및 Limit 검증
        pan_delta = (1.0 if pan_dir == "right" else -1.0) * pan_spd * 0.1
        tilt_delta = (1.0 if tilt_dir == "down" else -1.0) * tilt_spd * 0.1
        zoom_delta = (1.0 if zoom_dir == "wide" else -1.0) * zoom_spd * 0.1

        if abs(self.accumulated_pan_step + pan_delta) > pan_limit:
            logger.error(f"Correction Safety Limit Exceeded! Pan Limit: ±{pan_limit}°")
            await self.ptz.stop()
            return False

        if abs(self.accumulated_tilt_step + tilt_delta) > tilt_limit:
            logger.error(f"Correction Safety Limit Exceeded! Tilt Limit: ±{tilt_limit}°")
            await self.ptz.stop()
            return False

        if abs(self.accumulated_zoom_step + zoom_delta) > zoom_limit:
            logger.error(f"Correction Safety Limit Exceeded! Zoom Limit: ±{zoom_limit}%")
            await self.ptz.stop()
            return False

        # 물리적 이동 명령 전송
        if pan_dir != "stop" or tilt_dir != "stop":
            await self.ptz.move_relative(pan_spd, tilt_spd, pan_dir, tilt_dir)

        if zoom_dir != "stop":
            await self.ptz.zoom_relative(zoom_spd, zoom_dir)

        # 지정 Step Duration 동안 이동 실행 후 정지
        import asyncio
        await asyncio.sleep(step_duration)
        await self.ptz.stop()

        self.accumulated_pan_step += pan_delta
        self.accumulated_tilt_step += tilt_delta
        self.accumulated_zoom_step += zoom_delta

        return True
