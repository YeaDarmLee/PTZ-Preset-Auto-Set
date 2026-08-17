from typing import List, Optional
from fastapi import APIRouter, HTTPException
from app.database import get_db_connection, validate_base_live_presets
from app.models.preset import PresetCreate, PresetUpdate, PresetResponse

router = APIRouter(prefix="/api/presets", tags=["Presets"])

@router.get("", response_model=List[PresetResponse])
def get_presets(camera_id: Optional[int] = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if camera_id:
        cursor.execute("SELECT * FROM presets WHERE camera_id = ? ORDER BY sort_order ASC, id ASC", (camera_id,))
    else:
        cursor.execute("SELECT * FROM presets ORDER BY camera_id ASC, sort_order ASC, id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/{preset_id}", response_model=PresetResponse)
def get_preset(preset_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM presets WHERE id = ?", (preset_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Preset not found")
    return dict(row)

@router.post("", response_model=PresetResponse)
def create_preset(preset: PresetCreate):
    # 🚨 BASE / LIVE 교차 집합 중복 안전 검증
    if not validate_base_live_presets(preset.camera_id, preset.base_preset_no, preset.live_preset_no):
        raise HTTPException(
            status_code=400,
            detail=f"Safety Guard Conflict: BASE #{preset.base_preset_no} and LIVE #{preset.live_preset_no} conflict with existing presets on Camera #{preset.camera_id}"
        )

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO presets (
            camera_id, name, description, base_preset_no, live_preset_no, auto_set_enabled,
            target_mode, vertical_metric, scale_metric, person_count_policy,
            expected_person_count, minimum_person_count, maximum_person_count,
            roi_x1, roi_y1, roi_x2, roi_y2, target_x, target_y, target_scale,
            pan_limit, tilt_limit, zoom_limit, detection_confidence, stable_frames, timeout_sec, sort_order
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        preset.camera_id, preset.name, preset.description, preset.base_preset_no, preset.live_preset_no, preset.auto_set_enabled,
        preset.target_mode.value, preset.vertical_metric.value, preset.scale_metric.value, preset.person_count_policy.value,
        preset.expected_person_count, preset.minimum_person_count, preset.maximum_person_count,
        preset.roi_x1, preset.roi_y1, preset.roi_x2, preset.roi_y2, preset.target_x, preset.target_y, preset.target_scale,
        preset.pan_limit, preset.tilt_limit, preset.zoom_limit, preset.detection_confidence, preset.stable_frames, preset.timeout_sec, preset.sort_order
    ))
    conn.commit()
    p_id = cursor.lastrowid
    cursor.execute("SELECT * FROM presets WHERE id = ?", (p_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row)

@router.put("/{preset_id}", response_model=PresetResponse)
def update_preset(preset_id: int, preset: PresetUpdate):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT camera_id, base_preset_no, live_preset_no FROM presets WHERE id = ?", (preset_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Preset not found")

    cam_id = existing["camera_id"]
    new_base = preset.base_preset_no if preset.base_preset_no is not None else existing["base_preset_no"]
    new_live = preset.live_preset_no if preset.live_preset_no is not None else existing["live_preset_no"]

    # 🚨 BASE / LIVE 교차 중복 검증
    if not validate_base_live_presets(cam_id, new_base, new_live, exclude_preset_id=preset_id):
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=f"Safety Guard Conflict: BASE #{new_base} and LIVE #{new_live} intersect with existing presets on Camera #{cam_id}"
        )

    update_data = preset.dict(exclude_unset=True)
    if not update_data:
        conn.close()
        raise HTTPException(status_code=400, detail="No fields to update")

    # Enum 처리
    for k, v in list(update_data.items()):
        if hasattr(v, "value"):
            update_data[k] = v.value

    fields = [f"{k} = ?" for k in update_data.keys()]
    values = list(update_data.values())
    values.append(preset_id)

    cursor.execute(f"UPDATE presets SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", values)
    conn.commit()

    cursor.execute("SELECT * FROM presets WHERE id = ?", (preset_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row)

@router.delete("/{preset_id}")
def delete_preset(preset_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM presets WHERE id = ?", (preset_id,))
    conn.commit()
    conn.close()
    return {"message": "Preset deleted successfully"}
