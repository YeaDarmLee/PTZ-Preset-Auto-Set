import pytest
import sqlite3
from unittest.mock import MagicMock, AsyncMock
from app.database import get_db_connection
from app.routes.autoset import _run_autoset_retry_failed_bg

@pytest.mark.unit
@pytest.mark.asyncio
async def test_retry_failed_selects_only_failed_presets(in_memory_db, monkeypatch):
    """
    [RETRY FAILED SELECTION TEST]
    Preset 1 (SUCCESS), Preset 2 (FAILED), Preset 3 (SUCCESS) 상태일 때
    RETRY FAILED 실행 시 'FAILED' 상태인 Preset 2만 선별해서 재실행하고
    SUCCESS 상태인 Preset 1, 3은 재실행되지 않는지 검증.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Preset 시드 추가
    cursor.execute("""
    INSERT INTO presets (camera_id, name, base_preset_no, live_preset_no, auto_set_enabled, last_auto_set_status)
    VALUES (1, 'Preset SUCCESS 1', 10, 110, 1, 'SUCCESS')
    """)
    preset1_id = cursor.lastrowid

    cursor.execute("""
    INSERT INTO presets (camera_id, name, base_preset_no, live_preset_no, auto_set_enabled, last_auto_set_status)
    VALUES (1, 'Preset FAILED 2', 20, 120, 1, 'FAILED')
    """)
    preset2_id = cursor.lastrowid

    cursor.execute("""
    INSERT INTO presets (camera_id, name, base_preset_no, live_preset_no, auto_set_enabled, last_auto_set_status)
    VALUES (1, 'Preset SUCCESS 3', 30, 130, 1, 'SUCCESS')
    """)
    preset3_id = cursor.lastrowid

    conn.commit()
    conn.close()

    executed_preset_ids = []

    async def mock_run_preset_autoset(pid):
        executed_preset_ids.append(pid)
        return True

    monkeypatch.setattr(
        "app.routes.autoset.autoset_engine.run_preset_autoset",
        mock_run_preset_autoset
    )

    # Retry 실행
    await _run_autoset_retry_failed_bg()

    # FAILED 항목(preset2_id)만 1회 실행되었는지 검증
    assert executed_preset_ids == [preset2_id]
    assert preset1_id not in executed_preset_ids
    assert preset3_id not in executed_preset_ids
