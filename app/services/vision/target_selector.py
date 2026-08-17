import math
import logging
from enum import Enum
from typing import List, Optional
from app.services.vision.base_detector import PoseResult

logger = logging.getLogger(__name__)

class TargetMode(str, Enum):
    SINGLE = "SINGLE"
    GROUP = "GROUP"


class TargetSelector:
    """
    SINGLE Target Mode용 Target Person Lock 선택기
    - 한 AutoSet Cycle 동안 IoU / Center Distance / Pose Similarity 기반 Target Lock 유지
    """

    def __init__(self, iou_threshold: float = 0.3, distance_threshold: float = 0.25):
        self.iou_threshold = iou_threshold
        self.distance_threshold = distance_threshold
        self._locked_target: Optional[PoseResult] = None

    def reset_lock(self):
        """AutoSet 1회 실행 전 Target Lock 초기화"""
        self._locked_target = None

    def _calculate_iou(self, bboxA: List[float], bboxB: List[float]) -> float:
        xA = max(bboxA[0], bboxB[0])
        yA = max(bboxA[1], bboxB[1])
        xB = min(bboxA[2], bboxB[2])
        yB = min(bboxA[3], bboxB[3])

        interArea = max(0.0, xB - xA) * max(0.0, yB - yA)
        boxAArea = (bboxA[2] - bboxA[0]) * (bboxA[3] - bboxA[1])
        boxBArea = (bboxB[2] - bboxB[0]) * (bboxB[3] - bboxB[1])

        iou = interArea / float(boxAArea + boxBArea - interArea + 1e-6)
        return iou

    def select_target(self, candidates: List[PoseResult]) -> Optional[PoseResult]:
        """
        후보 인물 리스트 중 Target Lock 대상 또는 신규 Target 선정
        """
        if not candidates:
            return None

        # 1. 기존 Lock 된 Target이 없을 경우: 가장 confidence/bbox_score 가 높은 인물 선택
        if self._locked_target is None:
            best_candidate = max(candidates, key=lambda p: (p.bbox_score, p.height))
            self._locked_target = best_candidate
            logger.debug(f"TargetSelector: Initialized Lock on target at center ({best_candidate.center_x:.2f}, {best_candidate.center_y:.2f})")
            return best_candidate

        # 2. Lock 된 Target이 있을 경우: IoU 및 Center Distance로 가장 유사한 인물 연동 (Target Lock 유지)
        best_match: Optional[PoseResult] = None
        best_score = -1.0

        prev_bbox = self._locked_target.bbox
        prev_cx, prev_cy = self._locked_target.center_x, self._locked_target.center_y

        for cand in candidates:
            iou = self._calculate_iou(prev_bbox, cand.bbox)
            dist = math.hypot(cand.center_x - prev_cx, cand.center_y - prev_cy)

            # 유사도 스코어 산출
            if iou >= self.iou_threshold or dist <= self.distance_threshold:
                match_score = iou * 0.7 + (1.0 - min(1.0, dist)) * 0.3
                if match_score > best_score:
                    best_score = match_score
                    best_match = cand

        if best_match:
            self._locked_target = best_match
            return best_match
        else:
            # 돌발 상황으로 기존 Target을 놓친 경우: 가장 우수한 후보로 Re-lock
            logger.warning("TargetSelector: Lost Target Lock. Re-locking onto best candidate.")
            best_candidate = max(candidates, key=lambda p: (p.bbox_score, p.height))
            self._locked_target = best_candidate
            return best_candidate
