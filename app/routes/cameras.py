import re
import asyncio
import logging
from typing import List, Optional
import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, BackgroundTasks, status, Response
from app.database import get_db_connection
from app.models.camera import CameraCreate, CameraUpdate, CameraResponse, DraftTestRequest
from app.services.camera_health import camera_health_service, HealthCheckResult
from app.services.camera_manager import camera_manager
from app.services.state_manager import state_manager, HealthStatus
from app.services.autoset_engine import autoset_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cameras", tags=["Cameras"])

IP_REGEX = re.compile(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$")

def validate_camera_input(ip_address: str, visca_port: int, visca_protocol: str):
    if not IP_REGEX.match(ip_address):
        raise HTTPException(status_code=400, detail="Invalid IP Address format")
    if not (1 <= visca_port <= 65535):
        raise HTTPException(status_code=400, detail="Port must be between 1 and 65535")
    if visca_protocol.upper() not in ["UDP", "TCP"]:
        raise HTTPException(status_code=400, detail="Protocol must be UDP or TCP")

def mask_camera_dict(cam_dict: dict) -> dict:
    pwd = cam_dict.pop("rtsp_password", None)
    cam_dict["rtsp_password_set"] = bool(pwd)
    cam_dict["rtsp_url"] = camera_health_service.mask_rtsp_url(cam_dict["rtsp_url"])
    return cam_dict

def generate_placeholder_frame(text: str = "PTZ Stream Preview") -> bytes:
    """RTSP 미연결 시 사용할 1280x720 다크 그래픽 플레이스홀더 생성"""
    img = np.zeros((720, 1280, 3), dtype=np.uint8)
    img[:] = (26, 17, 11) # Dark navy (#0B0F19)
    
    # Grid lines
    for x in range(0, 1280, 80):
        cv2.line(img, (x, 0), (x, 720), (37, 29, 21), 1)
    for y in range(0, 720, 80):
        cv2.line(img, (0, y), (1280, y), (37, 29, 21), 1)

    cv2.putText(img, text, (400, 360), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (200, 200, 200), 2)
    cv2.putText(img, "Click and Drag mouse to set ROI area", (420, 410), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (150, 150, 150), 1)

    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()

@router.get("/{camera_id}/snapshot")
async def get_camera_snapshot(camera_id: int):
    """
    브라우저용 카메라 1프레임 JPEG 스냅샷 라우터
    (HTML img src에서 직접 사용 가능)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,))
    cam = cursor.fetchone()
    conn.close()

    if not cam:
        return Response(content=generate_placeholder_frame("Camera Not Found"), media_type="image/jpeg")

    full_rtsp = camera_health_service.build_full_rtsp_url(cam["rtsp_url"], cam["rtsp_username"], cam["rtsp_password"])

    loop = asyncio.get_running_loop()
    def _grab():
        try:
            cap = cv2.VideoCapture(full_rtsp, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not cap.isOpened():
                cap.release()
                return None
            ret, frame = cap.read()
            cap.release()
            if ret and frame is not None:
                _, buf = cv2.imencode(".jpg", frame)
                return buf.tobytes()
        except Exception:
            pass
        return None

    try:
        jpg_bytes = await asyncio.wait_for(loop.run_in_executor(None, _grab), timeout=2.5)
        if jpg_bytes:
            return Response(content=jpg_bytes, media_type="image/jpeg")
    except Exception:
        pass

    # 연결 실패 시 다크 플레이스홀더 제공
    return Response(content=generate_placeholder_frame(f"{cam['name']} ({cam['ip_address']}) - Standby"), media_type="image/jpeg")

@router.get("", response_model=List[CameraResponse])
def get_cameras():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cameras ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        result.append(mask_camera_dict(d))
    return result

@router.get("/{camera_id}", response_model=CameraResponse)
def get_camera(camera_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")
    return mask_camera_dict(dict(row))

@router.post("/test-connection")
async def test_draft_connection(draft: DraftTestRequest):
    validate_camera_input(draft.ip_address, draft.visca_port, draft.visca_protocol)
    
    res = await camera_health_service.test_draft_connection(
        ip=draft.ip_address,
        visca_port=draft.visca_port,
        visca_protocol=draft.visca_protocol,
        rtsp_url=draft.rtsp_url,
        username=draft.rtsp_username,
        password=draft.rtsp_password
    )
    return {
        "success": res.success,
        "visca": {
            "status": res.visca_status.value,
            "latency_ms": res.visca_latency_ms,
            "error": res.visca_error
        },
        "rtsp": {
            "status": res.rtsp_status.value,
            "resolution": res.rtsp_resolution,
            "error": res.rtsp_error
        }
    }

@router.post("/{camera_id}/test-connection")
async def test_existing_camera_connection(camera_id: int):
    health_lock = camera_manager.get_health_lock(camera_id)
    if health_lock.locked():
        raise HTTPException(status_code=409, detail="Health check already running for this camera")

    async with health_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,))
        cam = cursor.fetchone()
        conn.close()

        if not cam:
            raise HTTPException(status_code=404, detail="Camera not found")

        await state_manager.update_camera_health(camera_id, HealthStatus.TESTING, HealthStatus.TESTING)

        res = await camera_health_service.test_draft_connection(
            ip=cam["ip_address"],
            visca_port=cam["visca_port"],
            visca_protocol=cam["visca_protocol"],
            rtsp_url=cam["rtsp_url"],
            username=cam["rtsp_username"],
            password=cam["rtsp_password"]
        )

        await state_manager.update_camera_health(
            camera_id,
            res.visca_status,
            res.rtsp_status,
            res.visca_latency_ms,
            res.rtsp_resolution,
            res.visca_error or res.rtsp_error
        )

        return {
            "camera_id": camera_id,
            "success": res.success,
            "visca": {
                "status": res.visca_status.value,
                "latency_ms": res.visca_latency_ms,
                "error": res.visca_error
            },
            "rtsp": {
                "status": res.rtsp_status.value,
                "resolution": res.rtsp_resolution,
                "error": res.rtsp_error
            }
        }

@router.post("", response_model=CameraResponse)
def create_camera(camera: CameraCreate):
    validate_camera_input(camera.ip_address, camera.visca_port, camera.visca_protocol)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO cameras (name, ip_address, visca_port, visca_protocol, rtsp_url, rtsp_username, rtsp_password, enabled)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        camera.name, camera.ip_address, camera.visca_port, camera.visca_protocol,
        camera.rtsp_url, camera.rtsp_username, camera.rtsp_password, camera.enabled
    ))
    conn.commit()
    cam_id = cursor.lastrowid
    cursor.execute("SELECT * FROM cameras WHERE id = ?", (cam_id,))
    row = cursor.fetchone()
    conn.close()

    return mask_camera_dict(dict(row))

@router.put("/{camera_id}", response_model=CameraResponse)
async def update_camera(camera_id: int, camera: CameraUpdate):
    lock = camera_manager.get_lock(camera_id)
    if lock.locked():
        raise HTTPException(status_code=409, detail="Cannot update camera settings while AutoSet is running!")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Camera not found")

    update_data = camera.dict(exclude_unset=True)
    if not update_data:
        conn.close()
        raise HTTPException(status_code=400, detail="No fields to update")

    new_ip = update_data.get("ip_address", existing["ip_address"])
    new_port = update_data.get("visca_port", existing["visca_port"])
    new_proto = update_data.get("visca_protocol", existing["visca_protocol"])
    validate_camera_input(new_ip, new_port, new_proto)

    fields = [f"{k} = ?" for k in update_data.keys()]
    values = list(update_data.values())
    values.append(camera_id)

    cursor.execute(f"UPDATE cameras SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", values)
    conn.commit()

    cursor.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,))
    row = cursor.fetchone()
    conn.close()

    await camera_manager.atomic_reload_camera(camera_id, dict(row))

    return mask_camera_dict(dict(row))

@router.delete("/{camera_id}")
def delete_camera(camera_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM presets WHERE camera_id = ?", (camera_id,))
    preset_count = cursor.fetchone()[0]

    if preset_count > 0:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete Camera #{camera_id} because it has {preset_count} registered presets! Please disable the camera instead."
        )

    cursor.execute("DELETE FROM cameras WHERE id = ?", (camera_id,))
    conn.commit()
    conn.close()

    camera_manager.remove_camera(camera_id)
    return {"message": f"Camera #{camera_id} deleted successfully"}
