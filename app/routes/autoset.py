import asyncio
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.database import get_db_connection
from app.services.autoset_engine import autoset_engine
from app.services.state_manager import state_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/autoset", tags=["AutoSet Operations"])

async def _run_autoset_all_bg():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM presets WHERE auto_set_enabled = 1 ORDER BY camera_id ASC, sort_order ASC")
    rows = cursor.fetchall()
    conn.close()

    preset_ids = [r["id"] for r in rows]
    logger.info(f"Starting AUTO SET ALL for {len(preset_ids)} presets")

    for pid in preset_ids:
        if autoset_engine._cancel_requested:
            logger.warning("AUTO SET ALL stopped due to cancel request.")
            break
        await autoset_engine.run_preset_autoset(pid)

async def _run_autoset_retry_failed_bg():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM presets WHERE auto_set_enabled = 1 AND last_auto_set_status = 'FAILED' ORDER BY camera_id ASC, sort_order ASC")
    rows = cursor.fetchall()
    conn.close()

    preset_ids = [r["id"] for r in rows]
    logger.info(f"Starting RETRY FAILED for {len(preset_ids)} presets")

    for pid in preset_ids:
        if autoset_engine._cancel_requested:
            break
        await autoset_engine.run_preset_autoset(pid)

@router.post("/all")
async def trigger_autoset_all(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_autoset_all_bg)
    return {"message": "AUTO SET ALL started in background"}

@router.post("/retry-failed")
async def trigger_retry_failed(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_autoset_retry_failed_bg)
    return {"message": "RETRY FAILED started in background"}

@router.post("/cancel")
async def cancel_autoset():
    autoset_engine.cancel_all()
    return {"message": "AutoSet Cancellation requested"}

@router.post("/presets/{preset_id}")
async def trigger_single_preset(preset_id: int, background_tasks: BackgroundTasks):
    background_tasks.add_task(autoset_engine.run_preset_autoset, preset_id)
    return {"message": f"Single Preset AutoSet #{preset_id} started"}

@router.post("/reset-status")
async def reset_ui_status():
    """UI 상태만 READY로 리셋 (카메라 프리셋 미변경)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE presets SET last_auto_set_status = 'READY', last_error = NULL")
    conn.commit()
    conn.close()

    for pid in list(state_manager.preset_statuses.keys()):
        state_manager.preset_statuses[pid] = "READY"
    await state_manager.broadcast_event("system_reset", {"status": "READY"})
    return {"message": "UI Status reset to READY"}
