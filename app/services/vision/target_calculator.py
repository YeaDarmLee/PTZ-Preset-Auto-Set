import logging
from enum import Enum
from typing import Optional, List, Tuple
from app.services.vision.base_detector import PoseResult
from app.services.vision.group_calculator import GroupBBox, GroupBBoxCalculator
from app.services.vision.stabilizer import TargetMetrics, TargetStabilizer
from app.services.ptz.motion_controller import TargetError

logger = logging.getLogger(__name__)

class VerticalMetric(str, Enum):
    EYE_Y = "EYE_Y"
    BBOX_TOP = "BBOX_TOP"
    GROUP_TOP = "GROUP_TOP"
    GROUP_CENTER = "GROUP_CENTER"

class ScaleMetric(str, Enum):
    PERSON_HEIGHT = "PERSON_HEIGHT"
    SHOULDER_WIDTH = "SHOULDER_WIDTH"
    GROUP_WIDTH = "GROUP_WIDTH"
    GROUP_HEIGHT = "GROUP_HEIGHT"
    GROUP_BBOX = "GROUP_BBOX"

class TargetCalculator:
    """
    SINGLE 및 GROUP Target 데이터를 받아 vertical_metric & scale_metric 오차를 
    일관되게 계산하고 통일된 TargetError 구조체를 반환하는 계산기
    """

    def __init__(
        self,
        target_x: float = 0.5,
        target_y: float = 0.3,
        target_scale: float = 0.6,
        vertical_metric: VerticalMetric = VerticalMetric.EYE_Y,
        scale_metric: ScaleMetric = ScaleMetric.PERSON_HEIGHT
    ):
        self.target_x = target_x
        self.target_y = target_y
        self.target_scale = target_scale
        self.vertical_metric = vertical_metric
        self.scale_metric = scale_metric

    def extract_single_metrics(self, person: PoseResult) -> Optional[TargetMetrics]:
        """SINGLE 모드 1인 Pose에서 메트릭 추출"""
        if person is None:
            return None

        center_x = person.center_x

        # Vertical Metric 추출
        if self.vertical_metric == VerticalMetric.EYE_Y:
            l_eye = person.get_keypoint("left_eye")
            r_eye = person.get_keypoint("right_eye")
            if l_eye and r_eye and l_eye[2] > 0.3 and r_eye[2] > 0.3:
                vertical_val = (l_eye[1] + r_eye[1]) / 2.0
            else:
                nose = person.get_keypoint("nose")
                vertical_val = nose[1] if nose and nose[2] > 0.3 else person.bbox[1]
        elif self.vertical_metric == VerticalMetric.BBOX_TOP:
            vertical_val = person.bbox[1]
        else:
            vertical_val = person.center_y

        # Scale Metric 추출
        if self.scale_metric == ScaleMetric.SHOULDER_WIDTH:
            l_sh = person.get_keypoint("left_shoulder")
            r_sh = person.get_keypoint("right_shoulder")
            if l_sh and r_sh and l_sh[2] > 0.3 and r_sh[2] > 0.3:
                scale_val = abs(r_sh[0] - l_sh[0])
            else:
                scale_val = person.width
        else:  # PERSON_HEIGHT default
            scale_val = person.height

        return TargetMetrics(
            center_x=center_x,
            vertical_val=vertical_val,
            scale_val=scale_val,
            confidence=person.bbox_score
        )

    def extract_group_metrics(self, group_bbox: GroupBBox, conf: float) -> Optional[TargetMetrics]:
        """GROUP 모드 Virtual Group BBox에서 메트릭 추출"""
        if group_bbox is None:
            return None

        center_x = group_bbox.center_x

        # Vertical Metric (GROUP_TOP default)
        if self.vertical_metric == VerticalMetric.GROUP_CENTER:
            vertical_val = group_bbox.center_y
        else:
            vertical_val = group_bbox.top

        # Scale Metric (GROUP_WIDTH default)
        if self.scale_metric == ScaleMetric.GROUP_HEIGHT:
            scale_val = group_bbox.height
        elif self.scale_metric == ScaleMetric.GROUP_BBOX:
            scale_val = max(group_bbox.width, group_bbox.height)
        else:
            scale_val = group_bbox.width

        return TargetMetrics(
            center_x=center_x,
            vertical_val=vertical_val,
            scale_val=scale_val,
            confidence=conf
        )

    def calculate_error(self, stable_metrics: TargetMetrics) -> TargetError:
        """
        안정화된 TargetMetrics를 바탕으로 TargetError 반환
        """
        if stable_metrics is None:
            return TargetError(
                x_error=0.0, y_error=0.0, scale_error=0.0, confidence=0.0, valid=False, error_reason="No stable target metrics"
            )

        x_error = stable_metrics.center_x - self.target_x
        y_error = stable_metrics.vertical_val - self.target_y
        scale_error = (stable_metrics.scale_val - self.target_scale) / max(0.01, self.target_scale)

        return TargetError(
            x_error=x_error,
            y_error=y_error,
            scale_error=scale_error,
            confidence=stable_metrics.confidence,
            valid=True,
            error_reason=None
        )
