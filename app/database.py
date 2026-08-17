import sqlite3
import logging
from typing import Generator, Optional
from app.config import settings

logger = logging.getLogger(__name__)

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    """데이터베이스 테이블 자동 생성 및 초기 데이터 삽입"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Cameras
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cameras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        ip_address TEXT NOT NULL,
        visca_port INTEGER DEFAULT 52381,
        visca_protocol TEXT DEFAULT 'UDP',
        rtsp_url TEXT NOT NULL,
        rtsp_username TEXT,
        rtsp_password TEXT,
        enabled BOOLEAN DEFAULT 1,
        connection_status TEXT DEFAULT 'DISCONNECTED',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Presets
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS presets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        camera_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        
        base_preset_no INTEGER NOT NULL,
        live_preset_no INTEGER NOT NULL,
        auto_set_enabled BOOLEAN DEFAULT 1,
        
        target_mode TEXT DEFAULT 'SINGLE',
        vertical_metric TEXT DEFAULT 'EYE_Y',
        scale_metric TEXT DEFAULT 'PERSON_HEIGHT',
        person_count_policy TEXT DEFAULT 'FLEXIBLE',
        
        expected_person_count INTEGER NULL,
        minimum_person_count INTEGER NULL,
        maximum_person_count INTEGER NULL,
        
        roi_x1 REAL DEFAULT 0.0,
        roi_y1 REAL DEFAULT 0.0,
        roi_x2 REAL DEFAULT 1.0,
        roi_y2 REAL DEFAULT 1.0,
        
        target_x REAL DEFAULT 0.5,
        target_y REAL DEFAULT 0.3,
        target_scale REAL DEFAULT 0.6,
        
        pan_limit REAL DEFAULT 5.0,
        tilt_limit REAL DEFAULT 4.0,
        zoom_limit REAL DEFAULT 10.0,
        
        detection_confidence REAL DEFAULT 0.6,
        stable_frames INTEGER DEFAULT 10,
        timeout_sec INTEGER DEFAULT 15,
        
        sort_order INTEGER DEFAULT 0,
        
        last_auto_set_status TEXT DEFAULT 'READY',
        last_auto_set_time DATETIME,
        last_error TEXT,
        
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        
        FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE CASCADE,
        UNIQUE(camera_id, base_preset_no),
        UNIQUE(camera_id, live_preset_no)
    );
    """)

    # 3. Autoset Logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS autoset_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        camera_id INTEGER NOT NULL,
        preset_id INTEGER NOT NULL,
        base_preset_no INTEGER NOT NULL,
        live_preset_no INTEGER NOT NULL,
        
        target_mode TEXT DEFAULT 'SINGLE',
        detected_person_count INTEGER DEFAULT 0,
        detection_confidence REAL,
        initial_x_error REAL,
        initial_y_error REAL,
        final_x_error REAL,
        final_y_error REAL,
        
        correction_pan REAL,
        correction_tilt REAL,
        correction_zoom REAL,
        
        elapsed_time_ms INTEGER,
        result TEXT NOT NULL,
        error_message TEXT,
        
        FOREIGN KEY (camera_id) REFERENCES cameras(id),
        FOREIGN KEY (preset_id) REFERENCES presets(id)
    );
    """)

    # 4. System Settings
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        description TEXT
    );
    """)

    # 5. Auto Set Tuning Settings (Global, Camera, Preset Override)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS auto_set_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scope TEXT NOT NULL CHECK(scope IN ('GLOBAL', 'CAMERA', 'PRESET')),
        camera_id INTEGER NULL,
        preset_id INTEGER NULL,
        
        pan_gain REAL NULL,
        tilt_gain REAL NULL,
        deadzone_x REAL NULL,
        deadzone_y REAL NULL,
        tolerance_x REAL NULL,
        tolerance_y REAL NULL,
        
        max_pan_limit REAL NULL,
        max_tilt_limit REAL NULL,
        min_correction REAL NULL,
        
        pan_speed INTEGER NULL,
        tilt_speed INTEGER NULL,
        
        max_iterations INTEGER NULL,
        correction_interval_ms INTEGER NULL,
        
        detection_confidence_threshold REAL NULL,
        pose_confidence_threshold REAL NULL,
        
        target_selection_policy TEXT NULL,
        enable_zoom_correction BOOLEAN DEFAULT 0,
        
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        
        FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE CASCADE,
        FOREIGN KEY (preset_id) REFERENCES presets(id) ON DELETE CASCADE,
        
        CHECK (
            (scope = 'GLOBAL' AND camera_id IS NULL AND preset_id IS NULL) OR
            (scope = 'CAMERA' AND camera_id IS NOT NULL AND preset_id IS NULL) OR
            (scope = 'PRESET' AND camera_id IS NOT NULL AND preset_id IS NOT NULL)
        )
    );
    """)

    # SQLite Partial Unique Indexes for Scope NULL Safety
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_autoset_global ON auto_set_settings(scope) WHERE scope = 'GLOBAL';")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_autoset_camera ON auto_set_settings(camera_id) WHERE scope = 'CAMERA';")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_autoset_preset ON auto_set_settings(preset_id) WHERE scope = 'PRESET';")

    conn.commit()

    # 🚨 마이그레이션: 기존 DB에 rtsp_username, rtsp_password 컬럼이 없을 경우 자동으로 컬럼 추가
    cursor.execute("PRAGMA table_info(cameras);")
    existing_cols = [row[1] for row in cursor.fetchall()]
    if "rtsp_username" not in existing_cols:
        logger.info("Migrating DB: Adding rtsp_username column to cameras table...")
        cursor.execute("ALTER TABLE cameras ADD COLUMN rtsp_username TEXT;")
    if "rtsp_password" not in existing_cols:
        logger.info("Migrating DB: Adding rtsp_password column to cameras table...")
        cursor.execute("ALTER TABLE cameras ADD COLUMN rtsp_password TEXT;")
    conn.commit()

    # 초기 카메라 7대 샘플 데이터가 없으면 자동 등록 (교회 요구사항 CAM 1~7)
    cursor.execute("SELECT COUNT(*) FROM cameras;")
    if cursor.fetchone()[0] == 0:
        logger.info("Seeding initial 7 cameras data...")
        sample_cameras = [
            ("CAM 1", "192.168.1.101", 52381, "UDP", "rtsp://192.168.1.101:554/stream1"),
            ("CAM 2", "192.168.1.102", 52381, "UDP", "rtsp://192.168.1.102:554/stream1"),
            ("CAM 3", "192.168.1.103", 52381, "UDP", "rtsp://192.168.1.103:554/stream1"),
            ("CAM 4", "192.168.1.104", 52381, "UDP", "rtsp://192.168.1.104:554/stream1"),
            ("CAM 5", "192.168.1.105", 52381, "UDP", "rtsp://192.168.1.105:554/stream1"),
            ("CAM 6", "192.168.1.106", 52381, "UDP", "rtsp://192.168.1.106:554/stream1"),
            ("CAM 7", "192.168.1.107", 52381, "UDP", "rtsp://192.168.1.107:554/stream1"),
        ]
        cursor.executemany(
            "INSERT INTO cameras (name, ip_address, visca_port, visca_protocol, rtsp_url) VALUES (?, ?, ?, ?, ?)",
            sample_cameras
        )
        conn.commit()

        # CAM 1 기본 프리셋 추가
        cursor.execute("""
        INSERT INTO presets (camera_id, name, base_preset_no, live_preset_no, auto_set_enabled, target_mode, vertical_metric)
        VALUES (1, '설교자 Close', 1, 101, 1, 'SINGLE', 'EYE_Y');
        """)
        cursor.execute("""
        INSERT INTO presets (camera_id, name, base_preset_no, live_preset_no, auto_set_enabled, target_mode, vertical_metric, person_count_policy, expected_person_count)
        VALUES (1, '찬양팀 4인 Shot', 2, 102, 1, 'GROUP', 'GROUP_TOP', 'STRICT', 4);
        """)
        conn.commit()

    conn.close()
    logger.info("Database initialized successfully.")


def validate_base_live_presets(camera_id: int, new_base_no: int, new_live_no: int, exclude_preset_id: Optional[int] = None) -> bool:
    """
    [CRITICAL SAFETY CHECK]
    동일 카메라 내 ALL BASE Presets ∩ ALL LIVE Presets = EMPTY 검증
    Returns:
        True (유효), False (교차 충돌로 교부)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    if exclude_preset_id:
        cursor.execute(
            "SELECT base_preset_no, live_preset_no FROM presets WHERE camera_id = ? AND id != ?",
            (camera_id, exclude_preset_id)
        )
    else:
        cursor.execute(
            "SELECT base_preset_no, live_preset_no FROM presets WHERE camera_id = ?",
            (camera_id,)
        )

    rows = cursor.fetchall()
    conn.close()

    base_set = {r["base_preset_no"] for r in rows}
    live_set = {r["live_preset_no"] for r in rows}

    base_set.add(new_base_no)
    live_set.add(new_live_no)

    # 교차 집합이 존재하는 경우 거부
    intersection = base_set.intersection(live_set)
    if intersection:
        logger.error(f"BASE/LIVE Preset Intersection Conflict Detected: {intersection}")
        return False

    return True
