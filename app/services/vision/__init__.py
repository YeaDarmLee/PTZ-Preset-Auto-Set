"""
Vision Service Package
"""
from app.services.vision.base_detector import PoseDetectorBase, PoseResult
from app.services.vision.rtmlib_detector import RTMLibPoseDetector
from app.services.vision.frame_grabber import FrameGrabber
from app.services.vision.target_selector import TargetSelector
from app.services.vision.group_member_selector import GroupMemberSelector, PersonCountPolicy
from app.services.vision.group_calculator import GroupBBox, GroupBBoxCalculator
from app.services.vision.stabilizer import TargetStabilizer, TargetMetrics
from app.services.vision.target_calculator import TargetCalculator, VerticalMetric, ScaleMetric
from app.services.vision.vision_worker import VisionWorkerPool

__all__ = [
    "PoseDetectorBase",
    "PoseResult",
    "RTMLibPoseDetector",
    "FrameGrabber",
    "TargetSelector",
    "GroupMemberSelector",
    "PersonCountPolicy",
    "GroupBBox",
    "GroupBBoxCalculator",
    "TargetStabilizer",
    "TargetMetrics",
    "TargetCalculator",
    "VerticalMetric",
    "ScaleMetric",
    "VisionWorkerPool",
]
