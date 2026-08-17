from dataclasses import dataclass
from typing import List, Optional
from app.services.vision.base_detector import PoseResult

@dataclass
class GroupBBox:
    x1: float
    y1: float
    x2: float
    y2: float
    center_x: float
    center_y: float
    top: float
    width: float
    height: float
    member_count: int

class GroupBBoxCalculator:
    """
    선정된 그룹 멤버 인물들의 Bounding Box 극값을 구하여 
    Virtual Group Bounding Box 및 메트릭을 산출하는 계산기
    """

    @staticmethod
    def calculate_group_bbox(members: List[PoseResult]) -> Optional[GroupBBox]:
        if not members:
            return None

        group_x1 = min(m.bbox[0] for m in members)
        group_y1 = min(m.bbox[1] for m in members)
        group_x2 = max(m.bbox[2] for m in members)
        group_y2 = max(m.bbox[3] for m in members)

        width = abs(group_x2 - group_x1)
        height = abs(group_y2 - group_y1)
        center_x = (group_x1 + group_x2) / 2.0
        center_y = (group_y1 + group_y2) / 2.0
        top = group_y1

        return GroupBBox(
            x1=group_x1,
            y1=group_y1,
            x2=group_x2,
            y2=group_y2,
            center_x=center_x,
            center_y=center_y,
            top=top,
            width=width,
            height=height,
            member_count=len(members)
        )
