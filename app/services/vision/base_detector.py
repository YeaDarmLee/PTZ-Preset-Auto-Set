from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

class PoseResult:
    """
    단일 인물 Detection & Pose 결과 데이터 클래스
    Semantic Keypoint 조회를 지원함
    """
    def __init__(
        self,
        bbox: List[float],              # [x1, y1, x2, y2] Full-frame normalized (0.0 ~ 1.0)
        bbox_score: float,              # Detection confidence
        keypoints: np.ndarray,          # Shape (N, 2) normalized (0.0 ~ 1.0)
        keypoint_scores: np.ndarray,    # Shape (N,)
        schema: Optional[List[str]] = None
    ):
        self.bbox = bbox
        self.bbox_score = bbox_score
        self.keypoints = keypoints
        self.keypoint_scores = keypoint_scores
        # COCO 17 Keypoints 기본 스키마
        self.schema = schema or [
            "nose", "left_eye", "right_eye", "left_ear", "right_ear",
            "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
            "left_wrist", "right_wrist", "left_hip", "right_hip",
            "left_knee", "right_knee", "left_ankle", "right_ankle"
        ]

    def get_keypoint(self, name: str) -> Optional[Tuple[float, float, float]]:
        """
        이름으로 keypoint (x, y, confidence) 반환 (0.0~1.0 normalized)
        """
        if name in self.schema:
            idx = self.schema.index(name)
            if idx < len(self.keypoints):
                x, y = self.keypoints[idx][0], self.keypoints[idx][1]
                conf = float(self.keypoint_scores[idx]) if idx < len(self.keypoint_scores) else 0.0
                return (float(x), float(y), conf)
        return None

    @property
    def center_x(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2.0

    @property
    def center_y(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2.0

    @property
    def height(self) -> float:
        return abs(self.bbox[3] - self.bbox[1])

    @property
    def width(self) -> float:
        return abs(self.bbox[2] - self.bbox[0])


class PoseDetectorBase(ABC):
    """
    Vision Pose Detector 추상 인터페이스
    (rtmlib / MediaPipe / YOLO 등 다양한 AI 엔진 교체 가능)
    """

    @abstractmethod
    def initialize(self, model_size: str = "m", device: str = "cpu") -> bool:
        """모델 및 추론 엔진 초기화"""
        pass

    @abstractmethod
    def detect(self, frame: np.ndarray, roi: Optional[Tuple[float, float, float, float]] = None) -> List[PoseResult]:
        """
        영상 프레임 및 ROI 영역(x1, y1, x2, y2 normalized)에서 인물 및 Pose Keypoint 추출
        Returns:
            PoseResult 객체 리스트
        """
        pass
