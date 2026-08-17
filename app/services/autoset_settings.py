import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
from app.database import get_db_connection

logger = logging.getLogger(__name__)

# SYSTEM HARD CLAMPS (Unit-neutral max step limits)
SYSTEM_HARD_MAX_PAN_DELTA = 15.0
SYSTEM_HARD_MAX_TILT_DELTA = 10.0
SYSTEM_HARD_MAX_ZOOM_DELTA = 20.0

# SYSTEM DEFAULT FALLBACK VALUES
SYSTEM_DEFAULTS = {
    "pan_gain": 18.0,
    "tilt_gain": 14.0,
    "deadzone_x": 0.03,
    "deadzone_y": 0.03,
    "tolerance_x": 0.03,
    "tolerance_y": 0.03,
    "max_pan_limit": 5.0,
    "max_tilt_limit": 4.0,
    "min_correction": 0.005,
    "pan_speed": 12,
    "tilt_speed": 10,
    "max_iterations": 10,
    "correction_interval_ms": 300,
    "detection_confidence_threshold": 0.60,
    "pose_confidence_threshold": 0.30,
    "target_selection_policy": "CENTER_CLOSEST",
    "enable_zoom_correction": False
}

@dataclass(frozen=True)
class EffectiveAutoSetSettings:
    """AutoSet 작업 실행 시 스레드/태스크 세이프한 불변(Immutable) Snapshot 객체"""
    pan_gain: float
    tilt_gain: float
    deadzone_x: float
    deadzone_y: float
    tolerance_x: float
    tolerance_y: float
    max_pan_limit: float
    max_tilt_limit: float
    min_correction: float
    pan_speed: int
    tilt_speed: int
    max_iterations: int
    correction_interval_ms: int
    detection_confidence_threshold: float
    pose_confidence_threshold: float
    target_selection_policy: str
    enable_zoom_correction: bool
    scope_resolved: str  # 'PRESET', 'CAMERA', 'GLOBAL', 'SYSTEM'


class AutoSetSettingsService:
    """
    3단계 필드 수준 상속 (Field-Level Merge: Preset -> Camera -> Global -> System Default)
    설정 서비스
    """

    def validate_settings(self, data: Dict[str, Any], scope: str, camera_id: Optional[int] = None, preset_id: Optional[int] = None) -> Tuple[bool, Optional[str]]:
        """설정값 수치 범위 및 계층 관계 사전 검증"""
        # Scope 검증
        if scope not in ("GLOBAL", "CAMERA", "PRESET"):
            return False, f"Invalid scope: {scope}"

        if scope == "GLOBAL" and (camera_id is not None or preset_id is not None):
            return False, "GLOBAL scope must not have camera_id or preset_id"
        if scope == "CAMERA" and (camera_id is None or preset_id is not None):
            return False, "CAMERA scope requires camera_id and no preset_id"
        if scope == "PRESET" and (camera_id is None or preset_id is None):
            return False, "PRESET scope requires both camera_id and preset_id"

        # Preset-Camera 소속 검증
        if scope == "PRESET" and preset_id is not None and camera_id is not None:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT camera_id FROM presets WHERE id = ?", (preset_id,))
            row = cursor.fetchone()
            conn.close()
            if not row or row["camera_id"] != camera_id:
                return False, f"Preset #{preset_id} does not belong to Camera #{camera_id}"

        # 수치 범위 검증
        if "pan_gain" in data and data["pan_gain"] is not None and data["pan_gain"] <= 0:
            return False, "pan_gain must be positive"
        if "tilt_gain" in data and data["tilt_gain"] is not None and data["tilt_gain"] <= 0:
            return False, "tilt_gain must be positive"

        if "pan_speed" in data and data["pan_speed"] is not None and not (1 <= data["pan_speed"] <= 24):
            return False, "pan_speed must be between 1 and 24"
        if "tilt_speed" in data and data["tilt_speed"] is not None and not (1 <= data["tilt_speed"] <= 20):
            return False, "tilt_speed must be between 1 and 20"

        # Tolerance >= Deadzone 검증
        dz_x = data.get("deadzone_x")
        tol_x = data.get("tolerance_x")
        if dz_x is not None and tol_x is not None and tol_x < dz_x:
            return False, "tolerance_x cannot be smaller than deadzone_x"

        dz_y = data.get("deadzone_y")
        tol_y = data.get("tolerance_y")
        if dz_y is not None and tol_y is not None and tol_y < dz_y:
            return False, "tolerance_y cannot be smaller than deadzone_y"

        return True, None

    def get_effective_settings(self, camera_id: Optional[int] = None, preset_id: Optional[int] = None) -> EffectiveAutoSetSettings:
        """
        필드 수준 상속 (Field-Level Merge) 처리:
        Preset Record -> Camera Record -> Global Record -> System Defaults
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        global_row = None
        camera_row = None
        preset_row = None

        # 1. Global Record
        cursor.execute("SELECT * FROM auto_set_settings WHERE scope = 'GLOBAL'")
        g_fetch = cursor.fetchone()
        if g_fetch:
            global_row = dict(g_fetch)

        # 2. Camera Record
        if camera_id:
            cursor.execute("SELECT * FROM auto_set_settings WHERE scope = 'CAMERA' AND camera_id = ?", (camera_id,))
            c_fetch = cursor.fetchone()
            if c_fetch:
                camera_row = dict(c_fetch)

        # 3. Preset Record
        if preset_id:
            cursor.execute("SELECT * FROM auto_set_settings WHERE scope = 'PRESET' AND preset_id = ?", (preset_id,))
            p_fetch = cursor.fetchone()
            if p_fetch:
                preset_row = dict(p_fetch)

        conn.close()

        resolved = {}
        highest_scope = "SYSTEM"

        for field_name, default_val in SYSTEM_DEFAULTS.items():
            val = None
            # Preset -> Camera -> Global -> System Default
            if preset_row and preset_row.get(field_name) is not None:
                val = preset_row[field_name]
                if highest_scope == "SYSTEM":
                    highest_scope = "PRESET"
            elif camera_row and camera_row.get(field_name) is not None:
                val = camera_row[field_name]
                if highest_scope in ("SYSTEM", "GLOBAL"):
                    highest_scope = "CAMERA"
            elif global_row and global_row.get(field_name) is not None:
                val = global_row[field_name]
                if highest_scope == "SYSTEM":
                    highest_scope = "GLOBAL"
            else:
                val = default_val

            resolved[field_name] = val

        return EffectiveAutoSetSettings(
            pan_gain=float(resolved["pan_gain"]),
            tilt_gain=float(resolved["tilt_gain"]),
            deadzone_x=float(resolved["deadzone_x"]),
            deadzone_y=float(resolved["deadzone_y"]),
            tolerance_x=float(resolved["tolerance_x"]),
            tolerance_y=float(resolved["tolerance_y"]),
            max_pan_limit=float(resolved["max_pan_limit"]),
            max_tilt_limit=float(resolved["max_tilt_limit"]),
            min_correction=float(resolved["min_correction"]),
            pan_speed=int(resolved["pan_speed"]),
            tilt_speed=int(resolved["tilt_speed"]),
            max_iterations=int(resolved["max_iterations"]),
            correction_interval_ms=int(resolved["correction_interval_ms"]),
            detection_confidence_threshold=float(resolved["detection_confidence_threshold"]),
            pose_confidence_threshold=float(resolved["pose_confidence_threshold"]),
            target_selection_policy=str(resolved["target_selection_policy"]),
            enable_zoom_correction=bool(resolved["enable_zoom_correction"]),
            scope_resolved=highest_scope
        )

    def get_effective_preview(self, camera_id: Optional[int] = None, preset_id: Optional[int] = None) -> Dict[str, Any]:
        """UI 표출용 설정 프리뷰 (값, 출처, User Soft Limit, System Hard Limit 통합)"""
        effective = self.get_effective_settings(camera_id, preset_id)

        return {
            "effective": effective,
            "system_hard_limits": {
                "max_pan_delta": SYSTEM_HARD_MAX_PAN_DELTA,
                "max_tilt_delta": SYSTEM_HARD_MAX_TILT_DELTA,
                "max_zoom_delta": SYSTEM_HARD_MAX_ZOOM_DELTA
            }
        }

    def save_settings(self, scope: str, camera_id: Optional[int], preset_id: Optional[int], data: Dict[str, Any]) -> bool:
        """Scope별 설정 UPSERT 수행 (updated_at = CURRENT_TIMESTAMP)"""
        valid, err = self.validate_settings(data, scope, camera_id, preset_id)
        if not valid:
            logger.error(f"Validation failed for save_settings: {err}")
            raise ValueError(err)

        conn = get_db_connection()
        cursor = conn.cursor()

        # UPSERT 로직
        fields = [
            "pan_gain", "tilt_gain", "deadzone_x", "deadzone_y", "tolerance_x", "tolerance_y",
            "max_pan_limit", "max_tilt_limit", "min_correction", "pan_speed", "tilt_speed",
            "max_iterations", "correction_interval_ms", "detection_confidence_threshold",
            "pose_confidence_threshold", "target_selection_policy", "enable_zoom_correction"
        ]

        val_dict = {f: data.get(f) for f in fields if f in data}

        if scope == "GLOBAL":
            cursor.execute("SELECT id FROM auto_set_settings WHERE scope = 'GLOBAL'")
        elif scope == "CAMERA":
            cursor.execute("SELECT id FROM auto_set_settings WHERE scope = 'CAMERA' AND camera_id = ?", (camera_id,))
        else:  # PRESET
            cursor.execute("SELECT id FROM auto_set_settings WHERE scope = 'PRESET' AND preset_id = ?", (preset_id,))

        existing = cursor.fetchone()

        if existing:
            rec_id = existing["id"]
            set_clauses = [f"{f} = ?" for f in val_dict.keys()]
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")
            sql = f"UPDATE auto_set_settings SET {', '.join(set_clauses)} WHERE id = ?"
            params = list(val_dict.values()) + [rec_id]
            cursor.execute(sql, params)
        else:
            cols = ["scope", "camera_id", "preset_id"] + list(val_dict.keys())
            placeholders = ["?"] * len(cols)
            sql = f"INSERT INTO auto_set_settings ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"
            params = [scope, camera_id, preset_id] + list(val_dict.values())
            cursor.execute(sql, params)

        conn.commit()
        conn.close()
        logger.info(f"Successfully saved AutoSet settings for scope={scope}, camera_id={camera_id}, preset_id={preset_id}")
        return True

    def delete_override(self, scope: str, camera_id: Optional[int] = None, preset_id: Optional[int] = None) -> bool:
        """Override 삭제 (상위 Scope 상속 복귀)"""
        conn = get_db_connection()
        cursor = conn.cursor()

        if scope == "PRESET" and preset_id:
            cursor.execute("DELETE FROM auto_set_settings WHERE scope = 'PRESET' AND preset_id = ?", (preset_id,))
        elif scope == "CAMERA" and camera_id:
            cursor.execute("DELETE FROM auto_set_settings WHERE scope = 'CAMERA' AND camera_id = ?", (camera_id,))
        elif scope == "GLOBAL":
            cursor.execute("DELETE FROM auto_set_settings WHERE scope = 'GLOBAL'")

        conn.commit()
        conn.close()
        logger.info(f"Deleted override for scope={scope}, camera_id={camera_id}, preset_id={preset_id}")
        return True

autoset_settings_service = AutoSetSettingsService()
