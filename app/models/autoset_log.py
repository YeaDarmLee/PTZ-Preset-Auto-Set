from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class AutoSetLogBase(BaseModel):
    camera_id: int
    preset_id: int
    base_preset_no: int
    live_preset_no: int
    target_mode: str = "SINGLE"
    detected_person_count: int = 0
    detection_confidence: Optional[float] = None
    initial_x_error: Optional[float] = None
    initial_y_error: Optional[float] = None
    final_x_error: Optional[float] = None
    final_y_error: Optional[float] = None
    correction_pan: Optional[float] = None
    correction_tilt: Optional[float] = None
    correction_zoom: Optional[float] = None
    elapsed_time_ms: Optional[int] = None
    result: str
    error_message: Optional[str] = None

class AutoSetLogResponse(AutoSetLogBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True
