import logging
import math
import asyncio
from dataclasses import dataclass
from typing import Optional, Tuple
from app.services.ptz.guard import ProtectedPTZController
from app.services.autoset_settings import (
    EffectiveAutoSetSettings,
    SYSTEM_HARD_MAX_PAN_DELTA,
    SYSTEM_HARD_MAX_TILT_DELTA,
    SYSTEM_HARD_MAX_ZOOM_DELTA
)

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
    TargetError(X, Y, Scale 오차)를 해석하여 P-Control 기반 
    Correction Delta 및 PTZ Exec Speed를 계산하고, Safety Limit 내에서 조율하는 컨트롤러
    """

    def __init__(
        self,
        ptz: ProtectedPTZController,
        p_gain_pan: float = 18.0,
        p_gain_tilt: float = 14.0,
        p_gain_zoom: float = 5.0,
        settings: Optional[EffectiveAutoSetSettings] = None
    ):
        self.ptz = ptz
        self.settings = settings

        # Direct values if settings is provided, else fallback to defaults
        self.p_gain_pan = settings.pan_gain if settings else p_gain_pan
        self.p_gain_tilt = settings.tilt_gain if settings else p_gain_tilt
        self.p_gain_zoom = p_gain_zoom

        self.deadzone_x = settings.deadzone_x if settings else 0.03
        self.deadzone_y = settings.deadzone_y if settings else 0.03
        self.min_correction = settings.min_correction if settings else 0.005

        self.max_pan_limit = min(settings.max_pan_limit, SYSTEM_HARD_MAX_PAN_DELTA) if settings else 5.0
        self.max_tilt_limit = min(settings.max_tilt_limit, SYSTEM_HARD_MAX_TILT_DELTA) if settings else 4.0

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
        [AXIS-INDEPENDENT DEAD ZONE & MIN CORRECTION DEADBAND APPLIED]
        Returns:
            (pan_speed, tilt_speed, pan_dir, tilt_dir, zoom_speed, zoom_dir)
        """
        # 1. 축별 독립 Dead Zone 및 Min Correction Deadband 평가
        raw_pan_delta = 0.0
        if abs(error.x_error) > self.deadzone_x:
            raw_pan_delta = error.x_error * self.p_gain_pan

        raw_tilt_delta = 0.0
        if abs(error.y_error) > self.deadzone_y:
            raw_tilt_delta = error.y_error * self.p_gain_tilt

        # Option A: Min Correction Deadband (헌팅 방지)
        if abs(raw_pan_delta) < self.min_correction:
            raw_pan_delta = 0.0
        if abs(raw_tilt_delta) < self.min_correction:
            raw_tilt_delta = 0.0

        # Pan 방향 및 속도
        pan_dir = "right" if raw_pan_delta > 0 else ("left" if raw_pan_delta < 0 else "stop")
        if self.settings:
            raw_pan_spd = int(min(24, max(1, self.settings.pan_speed * (abs(raw_pan_delta) / 10.0)))) if pan_dir != "stop" else 0
        else:
            raw_pan_spd = int(abs(error.x_error) * self.p_gain_pan)
        pan_speed = max(1, min(24, raw_pan_spd)) if pan_dir != "stop" else 0

        # Tilt 방향 및 속도
        tilt_dir = "down" if raw_tilt_delta > 0 else ("up" if raw_tilt_delta < 0 else "stop")
        if self.settings:
            raw_tilt_spd = int(min(20, max(1, self.settings.tilt_speed * (abs(raw_tilt_delta) / 10.0)))) if tilt_dir != "stop" else 0
        else:
            raw_tilt_spd = int(abs(error.y_error) * self.p_gain_tilt)
        tilt_speed = max(1, min(20, raw_tilt_spd)) if tilt_dir != "stop" else 0

        # Zoom 방향 및 속도 (Scale error)
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
        User Soft Limit & System Hard Clamp 2중 검증 적용
        """
        conf_thresh = self.settings.pose_confidence_threshold if self.settings else 0.3
        if not error.valid or error.confidence < conf_thresh:
            logger.warning(f"Motion step skipped due to invalid/low confidence ({error.confidence} < {conf_thresh}): {error}")
            return False

        pan_spd, tilt_spd, pan_dir, tilt_dir, zoom_spd, zoom_dir = self.calculate_speeds(error)

        # 2중 안전 한계 Clamping (User Soft Limit vs. System Hard Clamp)
        effective_pan_limit = min(pan_limit, self.max_pan_limit, SYSTEM_HARD_MAX_PAN_DELTA)
        effective_tilt_limit = min(tilt_limit, self.max_tilt_limit, SYSTEM_HARD_MAX_TILT_DELTA)
        effective_zoom_limit = min(zoom_limit, SYSTEM_HARD_MAX_ZOOM_DELTA)

        pan_delta = (1.0 if pan_dir == "right" else -1.0) * pan_spd * 0.1
        tilt_delta = (1.0 if tilt_dir == "down" else -1.0) * tilt_spd * 0.1
        zoom_delta = (1.0 if zoom_dir == "wide" else -1.0) * zoom_spd * 0.1

        if abs(self.accumulated_pan_step + pan_delta) > effective_pan_limit:
            logger.error(f"Correction Safety Limit Exceeded! Pan Limit: ±{effective_pan_limit}")
            await self.ptz.stop()
            return False

        if abs(self.accumulated_tilt_step + tilt_delta) > effective_tilt_limit:
            logger.error(f"Correction Safety Limit Exceeded! Tilt Limit: ±{effective_tilt_limit}")
            await self.ptz.stop()
            return False

        if abs(self.accumulated_zoom_step + zoom_delta) > effective_zoom_limit:
            logger.error(f"Correction Safety Limit Exceeded! Zoom Limit: ±{effective_zoom_limit}")
            await self.ptz.stop()
            return False

        # 물리적 이동 명령 전송
        if pan_dir != "stop" or tilt_dir != "stop":
            await self.ptz.move_relative(pan_spd, tilt_spd, pan_dir, tilt_dir)

        if zoom_dir != "stop":
            await self.ptz.zoom_relative(zoom_spd, zoom_dir)

        await asyncio.sleep(step_duration)
        await self.ptz.stop()

        self.accumulated_pan_step += pan_delta
        self.accumulated_tilt_step += tilt_delta
        self.accumulated_zoom_step += zoom_delta

        return True
