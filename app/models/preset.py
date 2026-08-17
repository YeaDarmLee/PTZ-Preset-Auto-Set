from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.services.vision.target_selector import TargetMode
from app.services.vision.target_calculator import VerticalMetric, ScaleMetric
from app.services.vision.group_member_selector import PersonCountPolicy

class PresetBase(BaseModel):
    camera_id: int
    name: str
    description: Optional[str] = None
    
    base_preset_no: int
    live_preset_no: int
    auto_set_enabled: bool = True
    
    target_mode: TargetMode = TargetMode.SINGLE
    vertical_metric: VerticalMetric = VerticalMetric.EYE_Y
    scale_metric: ScaleMetric = ScaleMetric.PERSON_HEIGHT
    person_count_policy: PersonCountPolicy = PersonCountPolicy.FLEXIBLE
    
    expected_person_count: Optional[int] = None
    minimum_person_count: Optional[int] = None
    maximum_person_count: Optional[int] = None
    
    roi_x1: float = Field(default=0.0, ge=0.0, le=1.0)
    roi_y1: float = Field(default=0.0, ge=0.0, le=1.0)
    roi_x2: float = Field(default=1.0, ge=0.0, le=1.0)
    roi_y2: float = Field(default=1.0, ge=0.0, le=1.0)
    
    target_x: float = Field(default=0.5, ge=0.0, le=1.0)
    target_y: float = Field(default=0.3, ge=0.0, le=1.0)
    target_scale: float = Field(default=0.6, ge=0.0, le=1.0)
    
    pan_limit: float = 5.0
    tilt_limit: float = 4.0
    zoom_limit: float = 10.0
    
    detection_confidence: float = 0.6
    stable_frames: int = 10
    timeout_sec: int = 15
    sort_order: int = 0

class PresetCreate(PresetBase):
    pass

class PresetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    base_preset_no: Optional[int] = None
    live_preset_no: Optional[int] = None
    auto_set_enabled: Optional[bool] = None
    
    target_mode: Optional[TargetMode] = None
    vertical_metric: Optional[VerticalMetric] = None
    scale_metric: Optional[ScaleMetric] = None
    person_count_policy: Optional[PersonCountPolicy] = None
    
    expected_person_count: Optional[int] = None
    minimum_person_count: Optional[int] = None
    maximum_person_count: Optional[int] = None
    
    roi_x1: Optional[float] = None
    roi_y1: Optional[float] = None
    roi_x2: Optional[float] = None
    roi_y2: Optional[float] = None
    
    target_x: Optional[float] = None
    target_y: Optional[float] = None
    target_scale: Optional[float] = None
    
    pan_limit: Optional[float] = None
    tilt_limit: Optional[float] = None
    zoom_limit: Optional[float] = None
    
    detection_confidence: Optional[float] = None
    stable_frames: Optional[int] = None
    timeout_sec: Optional[int] = None
    sort_order: Optional[int] = None

class PresetResponse(PresetBase):
    id: int
    last_auto_set_status: str
    last_auto_set_time: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
