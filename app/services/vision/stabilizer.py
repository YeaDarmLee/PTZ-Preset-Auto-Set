from collections import deque
from dataclasses import dataclass
from typing import List, Optional
import numpy as np

@dataclass
class TargetMetrics:
    """Stabilizer 입출력용 구도 메트릭 구조체"""
    center_x: float
    vertical_val: float    # EYE_Y, BBOX_TOP, GROUP_TOP 등의 메트릭 값
    scale_val: float       # PERSON_HEIGHT, SHOULDER_WIDTH, GROUP_WIDTH 등의 메트릭 값
    confidence: float

class TargetStabilizer:
    """
    최근 N개 프레임의 구도 메트릭을 수집하여 
    Median / Trimmed Mean 필터링으로 단일 프레임 튀는 현상을 방지하는 Stabilizer
    """

    def __init__(self, window_size: int = 10):
        self.window_size = window_size
        self._history: deque[TargetMetrics] = deque(maxlen=window_size)

    def reset(self):
        """버퍼 초기화"""
        self._history.clear()

    def add_sample(self, sample: TargetMetrics) -> Optional[TargetMetrics]:
        """
        새 프레임 샘플 추가 및 안정화된 Stable Target Metrics 반환
        Returns:
            윈도우 크기에 도달하면 Stable TargetMetrics 반환, 부족하면 None
        """
        self._history.append(sample)
        if len(self._history) < self.window_size:
            return None

        # 윈도우 데이터 기반 Median / Trimmed Mean 계산
        cx_vals = [m.center_x for m in self._history]
        v_vals = [m.vertical_val for m in self._history]
        s_vals = [m.scale_val for m in self._history]
        conf_vals = [m.confidence for m in self._history]

        stable_cx = float(np.median(cx_vals))
        stable_v = float(np.median(v_vals))
        stable_s = float(np.median(s_vals))
        mean_conf = float(np.mean(conf_vals))

        return TargetMetrics(
            center_x=stable_cx,
            vertical_val=stable_v,
            scale_val=stable_s,
            confidence=mean_conf
        )
