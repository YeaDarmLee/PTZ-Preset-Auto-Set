from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class CameraBase(BaseModel):
    name: str
    ip_address: str
    visca_port: int = 52381
    visca_protocol: str = "UDP"
    rtsp_url: str
    rtsp_username: Optional[str] = None
    enabled: bool = True

class CameraCreate(CameraBase):
    rtsp_password: Optional[str] = None

class CameraUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = None
    visca_port: Optional[int] = None
    visca_protocol: Optional[str] = None
    rtsp_url: Optional[str] = None
    rtsp_username: Optional[str] = None
    rtsp_password: Optional[str] = None
    enabled: Optional[bool] = None

class CameraResponse(CameraBase):
    id: int
    connection_status: str = "UNKNOWN"
    rtsp_password_set: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class DraftTestRequest(BaseModel):
    ip_address: str
    visca_port: int = 52381
    visca_protocol: str = "UDP"
    rtsp_url: str
    rtsp_username: Optional[str] = None
    rtsp_password: Optional[str] = None
