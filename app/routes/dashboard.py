from fastapi import APIRouter, Request, HTTPException
from fastapi.templating import Jinja2Templates
from app.config import settings
from app.database import get_db_connection
from app.services.camera_health import camera_health_service

router = APIRouter(tags=["Dashboard"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
def render_dashboard(request: Request):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cameras ORDER BY id ASC")
    cameras = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT p.*, c.name as camera_name FROM presets p JOIN cameras c ON p.camera_id = c.id ORDER BY c.id ASC, p.sort_order ASC")
    presets = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # RTSP URL 마스킹
    for c in cameras:
        c["rtsp_url_masked"] = camera_health_service.mask_rtsp_url(c["rtsp_url"])

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "cameras": cameras, "presets": presets, "app_name": settings.APP_NAME}
    )

@router.get("/cameras")
def render_camera_list(request: Request):
    """카메라 전용 관리 및 추가/수정 페이지"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cameras ORDER BY id ASC")
    cameras = [dict(r) for r in cursor.fetchall()]
    conn.close()

    for c in cameras:
        c["rtsp_url_masked"] = camera_health_service.mask_rtsp_url(c["rtsp_url"])
        c["rtsp_password_set"] = bool(c.get("rtsp_password"))

    return templates.TemplateResponse(
        "camera_list.html",
        {"request": request, "cameras": cameras}
    )

@router.get("/cameras/{camera_id}/presets")
def render_camera_presets(camera_id: int, request: Request):
    """특정 카메라의 전용 프리셋 관리 페이지"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,))
    cam = cursor.fetchone()
    if not cam:
        conn.close()
        raise HTTPException(status_code=404, detail="Camera not found")

    cursor.execute("SELECT * FROM presets WHERE camera_id = ? ORDER BY sort_order ASC, id ASC", (camera_id,))
    presets = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        "preset_list.html",
        {"request": request, "camera": dict(cam), "presets": presets}
    )

@router.get("/roi-editor/{preset_id}")
def render_roi_editor(preset_id: int, request: Request):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.*, c.name as camera_name, c.rtsp_url 
        FROM presets p JOIN cameras c ON p.camera_id = c.id 
        WHERE p.id = ?
    """, (preset_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return templates.TemplateResponse("dashboard.html", {"request": request, "error": "Preset not found"})
    
    return templates.TemplateResponse("roi_editor.html", {"request": request, "preset": dict(row)})
