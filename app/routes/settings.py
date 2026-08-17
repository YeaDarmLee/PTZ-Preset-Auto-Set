import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from app.services.autoset_settings import autoset_settings_service, SYSTEM_DEFAULTS
from app.services.autoset_engine import autoset_engine
from app.database import get_db_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings/auto-set", tags=["AutoSet Settings"])

class SettingsSaveRequest(BaseModel):
    scope: str  # 'GLOBAL', 'CAMERA', 'PRESET'
    camera_id: Optional[int] = None
    preset_id: Optional[int] = None
    pan_gain: Optional[float] = None
    tilt_gain: Optional[float] = None
    deadzone_x: Optional[float] = None
    deadzone_y: Optional[float] = None
    tolerance_x: Optional[float] = None
    tolerance_y: Optional[float] = None
    max_pan_limit: Optional[float] = None
    max_tilt_limit: Optional[float] = None
    min_correction: Optional[float] = None
    pan_speed: Optional[int] = None
    tilt_speed: Optional[int] = None
    max_iterations: Optional[int] = None
    correction_interval_ms: Optional[int] = None
    detection_confidence_threshold: Optional[float] = None
    pose_confidence_threshold: Optional[float] = None
    target_selection_policy: Optional[str] = None
    enable_zoom_correction: Optional[bool] = False


class CalculationTestRequest(BaseModel):
    target_x: float = 0.5
    target_y: float = 0.3
    detected_x: float = 0.6
    detected_y: float = 0.4
    camera_id: Optional[int] = None
    preset_id: Optional[int] = None


@router.get("")
def get_auto_set_settings(camera_id: Optional[int] = Query(None), preset_id: Optional[int] = Query(None)):
    """Global, Camera, Preset 설정 및 Effective Preview 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM auto_set_settings WHERE scope = 'GLOBAL'")
    g_row = cursor.fetchone()

    cursor.execute("SELECT * FROM auto_set_settings WHERE scope = 'CAMERA'")
    c_rows = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM auto_set_settings WHERE scope = 'PRESET'")
    p_rows = [dict(r) for r in cursor.fetchall()]

    conn.close()

    preview = autoset_settings_service.get_effective_preview(camera_id, preset_id)

    return {
        "global": dict(g_row) if g_row else None,
        "camera_overrides": c_rows,
        "preset_overrides": p_rows,
        "effective_preview": preview,
        "system_defaults": SYSTEM_DEFAULTS
    }


@router.post("")
def save_auto_set_settings(req: SettingsSaveRequest):
    """Scope별 (GLOBAL, CAMERA, PRESET) AutoSet 설정 UPSERT"""
    data = req.dict(exclude_unset=True)
    scope = req.scope
    camera_id = req.camera_id
    preset_id = req.preset_id

    try:
        autoset_settings_service.save_settings(scope, camera_id, preset_id, data)
        return {"message": f"Successfully saved settings for scope {scope}"}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {e}")


@router.delete("/override")
def delete_auto_set_override(
    scope: str = Query(...),
    camera_id: Optional[int] = Query(None),
    preset_id: Optional[int] = Query(None)
):
    """Override 삭제 (상위 Scope 상속 복귀)"""
    try:
        autoset_settings_service.delete_override(scope, camera_id, preset_id)
        return {"message": f"Successfully deleted override for scope {scope}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-calc")
def run_calculation_test(req: CalculationTestRequest):
    """[CALCULATION TEST] 카메라/RTSP/AI 미사용 pure math 계산 결과 테스트"""
    res = autoset_engine.run_calculation_test(
        target_x=req.target_x,
        target_y=req.target_y,
        detected_x=req.detected_x,
        detected_y=req.detected_y,
        camera_id=req.camera_id,
        preset_id=req.preset_id
    )
    return res


@router.post("/live-dry-run/{preset_id}")
async def run_live_dry_run(preset_id: int):
    """[LIVE DRY RUN] 라이브 프레임 + AI 감지 수행 (PTZ Move ❌, Preset Recall/Save ❌)"""
    res = await autoset_engine.run_live_dry_run(preset_id)
    return res
