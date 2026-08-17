import pytest
import numpy as np
from app.services.vision.base_detector import PoseResult
from app.services.vision.target_selector import TargetSelector
from app.services.vision.group_member_selector import GroupMemberSelector, PersonCountPolicy
from app.services.vision.group_calculator import GroupBBoxCalculator

def make_dummy_pose(x1, y1, x2, y2, score=0.9):
    kps = np.zeros((17, 2), dtype=np.float32)
    scores = np.ones(17, dtype=np.float32) * score
    return PoseResult(
        bbox=[x1, y1, x2, y2],
        bbox_score=score,
        keypoints=kps,
        keypoint_scores=scores
    )

@pytest.mark.unit
def test_target_selector_single_person():
    """TargetSelector가 N명 중 가장 적절한 1인을 정상 선택하는지 검증"""
    selector = TargetSelector()

    p1 = make_dummy_pose(0.1, 0.1, 0.3, 0.5, score=0.5)
    p2 = make_dummy_pose(0.4, 0.2, 0.6, 0.8, score=0.95)

    selected = selector.select_target([p1, p2])
    assert selected == p2
    assert selector.select_target([]) is None


@pytest.mark.unit
def test_group_member_selector_strict_policy():
    """STRICT 정책에서 인원수 미달/초과 시 reject(False)하는지 검증"""
    selector = GroupMemberSelector(policy=PersonCountPolicy.STRICT, expected_count=4)

    p1 = make_dummy_pose(0.1, 0.1, 0.2, 0.5)
    p2 = make_dummy_pose(0.3, 0.1, 0.4, 0.5)
    p3 = make_dummy_pose(0.5, 0.1, 0.6, 0.5)

    members, valid, reason = selector.select_group_members([p1, p2, p3])
    assert valid is False
    assert "Person count mismatch" in reason


@pytest.mark.unit
def test_group_bbox_calculator():
    """GroupBBoxCalculator가 N명의 멤버 바운딩 박스를 정확히 아우르는 Virtual Group BBox를 계산하는지 검증"""
    p1 = make_dummy_pose(0.1, 0.2, 0.3, 0.8) # x: 0.1~0.3, y: 0.2~0.8
    p2 = make_dummy_pose(0.5, 0.1, 0.9, 0.7) # x: 0.5~0.9, y: 0.1~0.7

    bbox = GroupBBoxCalculator.calculate_group_bbox([p1, p2])

    assert bbox is not None
    assert pytest.approx(bbox.x1, 0.001) == 0.1
    assert pytest.approx(bbox.y1, 0.001) == 0.1
    assert pytest.approx(bbox.x2, 0.001) == 0.9
    assert pytest.approx(bbox.y2, 0.001) == 0.8
    assert pytest.approx(bbox.width, 0.001) == 0.8
    assert pytest.approx(bbox.height, 0.001) == 0.7
