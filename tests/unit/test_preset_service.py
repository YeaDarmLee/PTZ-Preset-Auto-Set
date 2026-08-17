import pytest
import sqlite3
from unittest.mock import MagicMock, AsyncMock
from app.services.ptz.guard import ProtectedPTZController
from app.database import validate_base_live_presets, get_db_connection

@pytest.mark.unit
@pytest.mark.asyncio
async def test_protected_ptz_controller_base_save_blocked_hard_guard():
    """
    [CRITICAL SAFETY TEST]
    BASE Preset 저장 요청 시 ProtectedPTZController가 PermissionError를 발생시키고
    실제 하드웨어 raw_controller.save_preset이 절대로 호출되지 않는지(assert_not_called) 검증.
    """
    raw_mock = MagicMock()
    raw_mock.save_preset = AsyncMock(return_value=True)

    # BASE Preset = {1, 2}
    protected_ptz = ProtectedPTZController(raw_mock, protected_base_presets={1, 2})

    # BASE Preset 1번에 저장 시도 -> 차단 및 예외 발생
    with pytest.raises(PermissionError) as exc_info:
        await protected_ptz.save_preset(1)
    assert "OVERWRITE protected BASE preset #1" in str(exc_info.value)
    raw_mock.save_preset.assert_not_called()

    # BASE Preset 2번에 저장 시도 -> 차단 및 예외 발생
    with pytest.raises(PermissionError) as exc_info:
        await protected_ptz.save_preset(2)
    assert "OVERWRITE protected BASE preset #2" in str(exc_info.value)
    raw_mock.save_preset.assert_not_called()

    # LIVE Preset 101번 저장 시도 -> 정상 통과 및 호출 확인
    result = await protected_ptz.save_preset(101)
    assert result is True
    raw_mock.save_preset.assert_called_once_with(101)


@pytest.mark.unit
def test_validate_base_live_presets_same_number_blocked():
    """
    BASE와 LIVE 번호가 서로 동일한 경우 (예: BASE=1, LIVE=1)
    validate_base_live_presets validation에서 즉시 False를 반환하는지 검증.
    """
    # 동일 카메라에 BASE=10, LIVE=10 등록 시도 -> False
    is_valid = validate_base_live_presets(camera_id=1, new_base_no=10, new_live_no=10)
    assert is_valid is False


@pytest.mark.unit
def test_validate_base_live_presets_cross_conflict_blocked(in_memory_db):
    """
    기존 프리셋의 LIVE 번호와 새 프리셋의 BASE 번호가 교차 충돌하는 경우 거부되는지 검증.
    (기존 Preset: BASE=1, LIVE=101)
    """
    # 이미 DB에 (BASE=1, LIVE=101)이 존재하는 상태에서
    # 새 프리셋으로 BASE=101, LIVE=201 추가 시도 -> LIVE 101과 BASE 101 충돌로 False 반환
    is_valid = validate_base_live_presets(camera_id=1, new_base_no=101, new_live_no=201)
    assert is_valid is False

    # 정상 케이스: BASE=3, LIVE=103 -> True
    is_valid_ok = validate_base_live_presets(camera_id=1, new_base_no=3, new_live_no=103)
    assert is_valid_ok is True


@pytest.mark.unit
def test_nonexistent_preset_queries(in_memory_db):
    """존재하지 않는 프리셋 ID 조회 시 None 반환 처리 확인"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM presets WHERE id = ?", (99999,))
    row = cursor.fetchone()
    conn.close()
    assert row is None
