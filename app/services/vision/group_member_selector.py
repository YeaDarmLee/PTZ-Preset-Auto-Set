import math
import logging
from enum import Enum
from typing import List, Optional, Tuple
from app.services.vision.base_detector import PoseResult

logger = logging.getLogger(__name__)

class PersonCountPolicy(str, Enum):
    STRICT = "STRICT"      # expected_person_count와 정확히 일치 필수
    MINIMUM = "MINIMUM"    # minimum_person_count 이상이면 성공
    FLEXIBLE = "FLEXIBLE"  # ROI 내 모든 유효 인원 대상

class GroupMemberSelector:
    """
    GROUP Target Mode용 Group Member Lock & Person Count Policy 선택기
    - 한 AutoSet Cycle 동안 검출된 그룹 멤버들(Group Member Lock)을 고정
    - 후방 연주자/돌발 인물 추가 검출로 인한 BBox 급확대 차단
    """

    def __init__(
        self,
        policy: PersonCountPolicy = PersonCountPolicy.FLEXIBLE,
        expected_count: Optional[int] = None,
        min_count: Optional[int] = None,
        max_count: Optional[int] = None
    ):
        self.policy = policy
        self.expected_count = expected_count
        self.min_count = min_count
        self.max_count = max_count

        self._locked_members: List[PoseResult] = []
        self._is_locked = False

    def reset_lock(self):
        """AutoSet 1회 실행 전 Group Member Lock 초기화"""
        self._locked_members = []
        self._is_locked = False

    def _match_member(self, member: PoseResult, candidates: List[PoseResult]) -> Optional[PoseResult]:
        """기존 멤버 1인과 가장 매칭되는 후보 검색"""
        best_cand = None
        min_dist = 0.25  # Max distance threshold

        for cand in candidates:
            dist = math.hypot(cand.center_x - member.center_x, cand.center_y - member.center_y)
            if dist < min_dist:
                min_dist = dist
                best_cand = cand

        return best_cand

    def validate_person_count(self, count: int) -> Tuple[bool, Optional[str]]:
        """인원수 정책 검증"""
        if self.policy == PersonCountPolicy.STRICT:
            if self.expected_count is not None and count != self.expected_count:
                return False, f"Person count mismatch! Expected: {self.expected_count}, Detected: {count}"

        elif self.policy == PersonCountPolicy.MINIMUM:
            if self.min_count is not None and count < self.min_count:
                return False, f"Insufficient person count! Minimum: {self.min_count}, Detected: {count}"

        if self.max_count is not None and count > self.max_count:
            return False, f"Exceeded maximum person count! Maximum: {self.max_count}, Detected: {count}"

        return True, None

    def select_group_members(self, candidates: List[PoseResult]) -> Tuple[List[PoseResult], bool, Optional[str]]:
        """
        후보 인물들 중 Group Member 선택 및 Lock 적용
        Returns:
            (selected_members, valid, error_reason)
        """
        if not candidates:
            return [], False, "No person detected in ROI"

        # 1. 아직 Lock이 걸리지 않은 초기 단계
        if not self._is_locked:
            # 인원 수 필터링 및 정렬 (가장 b_score가 높은 순)
            candidates_sorted = sorted(candidates, key=lambda p: p.bbox_score, reverse=True)
            
            # max_count가 설정되어 있으면 상위 N개만 선택
            if self.max_count and len(candidates_sorted) > self.max_count:
                selected = candidates_sorted[:self.max_count]
            else:
                selected = candidates_sorted

            valid, reason = self.validate_person_count(len(selected))
            if not valid:
                return selected, False, reason

            # Group Member Lock 확정
            self._locked_members = selected
            self._is_locked = True
            logger.debug(f"GroupMemberSelector: Group Member Lock established on {len(selected)} persons.")
            return selected, True, None

        # 2. 이미 Group Member Lock이 걸린 경우: 기존 Lock 멤버와 가깝게 대응되는 인물만 선별 (외곽 돌발 검출자 제제)
        matched_members: List[PoseResult] = []
        for member in self._locked_members:
            matched = self._match_member(member, candidates)
            if matched:
                matched_members.append(matched)

        # 멤버 중 일부를 순간 잃어버렸더라도 유효성 검사
        valid, reason = self.validate_person_count(len(matched_members))
        if matched_members:
            self._locked_members = matched_members

        return matched_members, valid, reason
