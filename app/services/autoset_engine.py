import time
import asyncio
import logging
from typing import Dict, Any, Optional
from app.database import get_db_connection
from app.services.camera_manager import camera_manager
from app.services.state_manager import state_manager
from app.services.ptz.motion_controller import MotionController, TargetError
from app.services.vision.rtmlib_detector import RTMLibPoseDetector
from app.services.vision.vision_worker import VisionWorkerPool
from app.services.vision.frame_grabber import FrameGrabber
from app.services.vision.target_selector import TargetSelector, TargetMode
from app.services.vision.group_member_selector import GroupMemberSelector, PersonCountPolicy
from app.services.vision.group_calculator import GroupBBoxCalculator
from app.services.vision.stabilizer import TargetStabilizer
from app.services.vision.target_calculator import TargetCalculator, VerticalMetric, ScaleMetric
from app.services.autoset_settings import (
    autoset_settings_service,
    EffectiveAutoSetSettings,
    SYSTEM_HARD_MAX_PAN_DELTA,
    SYSTEM_HARD_MAX_TILT_DELTA
)

logger = logging.getLogger(__name__)

class AutoSetEngine:
    """
    Closed-Loop Auto Set 실행 엔진
    (Tolerance 사전 판정, STALLED 조기 종료, 불변 Settings Snapshot, 2단계 Dry Run 지원)
    """

    def __init__(self):
        self.detector = RTMLibPoseDetector()
        self.detector.initialize(model_size="m")
        self.worker_pool = VisionWorkerPool(self.detector)
        self._cancel_requested = False

    def cancel_all(self):
        """진행 중인 AutoSet 취소요청"""
        self._cancel_requested = True
        logger.warning("AutoSet Cancel requested!")

    async def run_preset_autoset(self, preset_id: int) -> bool:
        """
        단일 Preset에 대한 Closed-Loop Auto Set 전 과정 수행
        """
        self._cancel_requested = False
        start_time = time.time()

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.*, c.ip_address, c.visca_port, c.visca_protocol, c.rtsp_url 
                FROM presets p JOIN cameras c ON p.camera_id = c.id 
                WHERE p.id = ?
            """, (preset_id,))
            row = cursor.fetchone()
            conn.close()

            if not row:
                logger.error(f"Preset #{preset_id} not found in database.")
                return False
        except Exception as e:
            logger.error(f"Database error during run_preset_autoset: {e}")
            return False

        preset_data = dict(row)
        camera_id = preset_data["camera_id"]
        base_no = preset_data["base_preset_no"]
        live_no = preset_data["live_preset_no"]

        # 🚨 IMMUTABLE SETTINGS SNAPSHOTRESOLVE AT JOB START
        settings = autoset_settings_service.get_effective_settings(camera_id, preset_id)

        await state_manager.update_preset_status(camera_id, preset_id, "RUNNING")

        # 1. Auto Set Disabled 인 경우 처리
        if not preset_data["auto_set_enabled"]:
            logger.info(f"Preset '{preset_data['name']}' AutoSet Disabled. Copying BASE preset to LIVE.")
            ptz = camera_manager.get_protected_controller(camera_id)
            if ptz:
                await ptz.recall_preset(base_no)
                await asyncio.sleep(0.5)
                await ptz.save_preset(live_no)
            await state_manager.update_preset_status(camera_id, preset_id, "SUCCESS")
            return True

        # 카메라 단위 Async Lock 획득 (동일 카메라 중복 구동 방지)
        lock = camera_manager.get_lock(camera_id)
        async with lock:
            ptz = camera_manager.get_protected_controller(camera_id)
            if not ptz:
                await state_manager.update_preset_status(camera_id, preset_id, "FAILED", "PTZ Controller Error")
                return False

            motion_controller = MotionController(ptz, settings=settings)
            motion_controller.reset_accumulated_limits()

            frame_grabber = FrameGrabber(preset_data["rtsp_url"])
            frame_grabber.start()

            try:
                # STEP 1: BASE Preset Recall
                logger.info(f"Recalling BASE Preset #{base_no} for '{preset_data['name']}'")
                await ptz.recall_preset(base_no)

                # STEP 2: Settle Time 대기 및 RTSP Buffer Flushing
                await asyncio.sleep(1.0)
                frame_grabber.flush_buffer()

                target_mode = TargetMode(preset_data["target_mode"])
                vertical_metric = VerticalMetric(preset_data["vertical_metric"])
                scale_metric = ScaleMetric(preset_data["scale_metric"])
                count_policy = PersonCountPolicy(preset_data["person_count_policy"])

                roi = (preset_data["roi_x1"], preset_data["roi_y1"], preset_data["roi_x2"], preset_data["roi_y2"])

                calculator = TargetCalculator(
                    target_x=preset_data["target_x"],
                    target_y=preset_data["target_y"],
                    target_scale=preset_data["target_scale"],
                    vertical_metric=vertical_metric,
                    scale_metric=scale_metric
                )

                target_selector = TargetSelector()
                group_selector = GroupMemberSelector(
                    policy=count_policy,
                    expected_count=preset_data["expected_person_count"],
                    min_count=preset_data["minimum_person_count"],
                    max_count=preset_data["maximum_person_count"]
                )
                stabilizer = TargetStabilizer(window_size=preset_data["stable_frames"])

                success = False
                stalled = False
                final_error = None
                max_iterations = settings.max_iterations

                for iteration in range(max_iterations):
                    if self._cancel_requested:
                        logger.warning("AutoSet execution cancelled by user!")
                        await state_manager.update_preset_status(camera_id, preset_id, "FAILED", "Cancelled")
                        return False

                    frame, ts, gen = frame_grabber.get_latest_frame()
                    if frame is None:
                        await asyncio.sleep(0.1)
                        continue

                    candidates = await self.worker_pool.detect_async(frame, roi)
                    metrics_sample = None

                    if target_mode == TargetMode.SINGLE:
                        target_person = target_selector.select_target(candidates)
                        if target_person:
                            metrics_sample = calculator.extract_single_metrics(target_person)
                    else:  # GROUP Mode
                        members, valid, reason = group_selector.select_group_members(candidates)
                        if valid and members:
                            group_bbox = GroupBBoxCalculator.calculate_group_bbox(members)
                            if group_bbox:
                                avg_conf = sum(m.bbox_score for m in members) / len(members)
                                metrics_sample = calculator.extract_group_metrics(group_bbox, avg_conf)

                    if metrics_sample is None:
                        logger.warning(f"Iteration {iteration}: No valid target metrics sample found.")
                        await asyncio.sleep(0.2)
                        continue

                    stable_metrics = stabilizer.add_sample(metrics_sample)
                    if stable_metrics is None:
                        await asyncio.sleep(0.05)
                        continue

                    target_err = calculator.calculate_error(stable_metrics)
                    final_error = target_err

                    logger.info(
                        f"Iter {iteration} TargetError -> X: {target_err.x_error:.3f}, "
                        f"Y: {target_err.y_error:.3f}, Scale: {target_err.scale_error:.3f}"
                    )

                    # 🚨 SAFETY RULE 1: Target Tolerance 성공 판정을 PTZ 보정 계산보다 먼저 수행!
                    if (
                        abs(target_err.x_error) <= settings.tolerance_x and
                        abs(target_err.y_error) <= settings.tolerance_y and
                        abs(target_err.scale_error) <= 0.05
                    ):
                        logger.info(f"Target successfully converged on iteration {iteration} via Tolerance check!")
                        success = True
                        break

                    # 🚨 SAFETY RULE 2: Tolerance 미충족 상태에서 PTZ Delta가 0이면 STALLED 조기 종료!
                    pan_spd, tilt_spd, pan_dir, tilt_dir, _, _ = motion_controller.calculate_speeds(target_err)
                    if pan_dir == "stop" and tilt_dir == "stop":
                        logger.warning(
                            f"Iter {iteration}: Tolerance not met (X:{target_err.x_error:.3f}, Y:{target_err.y_error:.3f}), "
                            f"but PTZ delta is 0 due to DeadZone/MinCorrection. STALLED termination."
                        )
                        stalled = True
                        break

                    # 미세 보정 적용
                    step_ok = await motion_controller.apply_step_correction(
                        error=target_err,
                        pan_limit=preset_data["pan_limit"],
                        tilt_limit=preset_data["tilt_limit"],
                        zoom_limit=preset_data["zoom_limit"],
                        step_duration=0.15
                    )
                    if not step_ok:
                        logger.error("Step correction failed or limit exceeded!")
                        break

                    await asyncio.sleep(settings.correction_interval_ms / 1000.0)

                elapsed_ms = int((time.time() - start_time) * 1000)

                if success:
                    logger.info(f"Saving LIVE Preset #{live_no} for '{preset_data['name']}'")
                    await ptz.save_preset(live_no)
                    await state_manager.update_preset_status(camera_id, preset_id, "SUCCESS")
                    self._log_execution(preset_data, final_error, elapsed_ms, "SUCCESS")
                    return True
                elif stalled:
                    logger.warning(f"AutoSet STALLED for '{preset_data['name']}'. Preserving existing LIVE preset.")
                    await state_manager.update_preset_status(
                        camera_id, preset_id, "FAILED", "STALLED: No effective correction inside DeadZone/MinCorrection"
                    )
                    self._log_execution(preset_data, final_error, elapsed_ms, "FAILED", "STALLED: No effective correction")
                    return False
                else:
                    logger.warning(f"AutoSet FAILED for '{preset_data['name']}'. Preserving existing LIVE preset.")
                    await state_manager.update_preset_status(camera_id, preset_id, "FAILED", "Convergence Failed")
                    self._log_execution(preset_data, final_error, elapsed_ms, "FAILED", "Convergence or Limit Failed")
                    return False

            finally:
                frame_grabber.stop()

    def run_calculation_test(
        self,
        target_x: float,
        target_y: float,
        detected_x: float,
        detected_y: float,
        camera_id: Optional[int] = None,
        preset_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        [CALCULATION TEST - ZERO RTSP, ZERO AI, ZERO PTZ]
        입력 좌표 수치만으로 오차, Dead Zone 판정, Soft/Hard Clamping 및 보정 결과 계산
        """
        settings = autoset_settings_service.get_effective_settings(camera_id, preset_id)

        x_error = detected_x - target_x
        y_error = detected_y - target_y

        x_in_deadzone = abs(x_error) <= settings.deadzone_x
        y_in_deadzone = abs(y_error) <= settings.deadzone_y

        raw_pan_delta = 0.0 if x_in_deadzone else x_error * settings.pan_gain
        raw_tilt_delta = 0.0 if y_in_deadzone else y_error * settings.tilt_gain

        # Min correction deadband
        if abs(raw_pan_delta) < settings.min_correction:
            raw_pan_delta = 0.0
        if abs(raw_tilt_delta) < settings.min_correction:
            raw_tilt_delta = 0.0

        user_soft_pan = min(abs(raw_pan_delta), settings.max_pan_limit) * (1 if raw_pan_delta >= 0 else -1)
        user_soft_tilt = min(abs(raw_tilt_delta), settings.max_tilt_limit) * (1 if raw_tilt_delta >= 0 else -1)

        final_pan_delta = min(abs(user_soft_pan), SYSTEM_HARD_MAX_PAN_DELTA) * (1 if user_soft_pan >= 0 else -1)
        final_tilt_delta = min(abs(user_soft_tilt), SYSTEM_HARD_MAX_TILT_DELTA) * (1 if user_soft_tilt >= 0 else -1)

        tolerance_met = (abs(x_error) <= settings.tolerance_x) and (abs(y_error) <= settings.tolerance_y)

        return {
            "inputs": {
                "target_x": target_x, "target_y": target_y,
                "detected_x": detected_x, "detected_y": detected_y
            },
            "errors": {"x_error": round(x_error, 4), "y_error": round(y_error, 4)},
            "deadzone_status": {
                "x_in_deadzone": x_in_deadzone,
                "y_in_deadzone": y_in_deadzone,
                "fully_in_deadzone": x_in_deadzone and y_in_deadzone
            },
            "tolerance_met": tolerance_met,
            "calculated_deltas": {
                "raw_pan_delta": round(raw_pan_delta, 4),
                "raw_tilt_delta": round(raw_tilt_delta, 4),
                "user_soft_clamped_pan": round(user_soft_pan, 4),
                "user_soft_clamped_tilt": round(user_soft_tilt, 4),
                "final_hard_clamped_pan": round(final_pan_delta, 4),
                "final_hard_clamped_tilt": round(final_tilt_delta, 4)
            },
            "effective_settings_used": settings
        }

    async def run_live_dry_run(self, preset_id: int) -> Dict[str, Any]:
        """
        [LIVE DRY RUN - RTSP READ OK, AI READ OK, PTZ MOVE ❌, PRESET RECALL/SAVE ❌]
        라이브 카메라 프레임 수신 및 인물 감지까지 수행하나 PTZ 하드웨어 구동은 100% 스킵
        """
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
            return {"success": False, "error": "Preset not found"}

        preset_data = dict(row)
        camera_id = preset_data["camera_id"]

        settings = autoset_settings_service.get_effective_settings(camera_id, preset_id)
        frame_grabber = FrameGrabber(preset_data["rtsp_url"])
        frame_grabber.start()

        try:
            await asyncio.sleep(0.5)
            frame_grabber.flush_buffer()
            frame, _, _ = frame_grabber.get_latest_frame()

            if frame is None:
                return {"success": False, "error": "Failed to grab live RTSP frame"}

            roi = (preset_data["roi_x1"], preset_data["roi_y1"], preset_data["roi_x2"], preset_data["roi_y2"])
            candidates = await self.worker_pool.detect_async(frame, roi)

            target_selector = TargetSelector()
            target_person = target_selector.select_target(candidates)

            if not target_person:
                return {
                    "success": False,
                    "preset_id": preset_id,
                    "preset_name": preset_data["name"],
                    "camera_name": preset_data["camera_name"],
                    "warning_notice": "⚠️ Preset Recall은 수행하지 않으며, 현재 카메라 화면을 분석합니다.",
                    "detected_person_count": 0,
                    "message": "No person detected in specified ROI"
                }

            calculator = TargetCalculator(
                target_x=preset_data["target_x"],
                target_y=preset_data["target_y"],
                target_scale=preset_data["target_scale"]
            )
            metrics = calculator.extract_single_metrics(target_person)
            target_err = calculator.calculate_error(metrics)

            calc_result = self.run_calculation_test(
                preset_data["target_x"], preset_data["target_y"],
                metrics.center_x, metrics.vertical_val,
                camera_id=camera_id, preset_id=preset_id
            )

            return {
                "success": True,
                "preset_id": preset_id,
                "preset_name": preset_data["name"],
                "camera_name": preset_data["camera_name"],
                "warning_notice": "⚠️ Live Dry Run: Preset Recall은 수행하지 않으며 현재 카메라 화면을 기준 ROI/Target과 비교합니다.",
                "detected_person_count": len(candidates),
                "person_confidence": target_person.bbox_score,
                "calculation_details": calc_result,
                "ptz_moved": False,
                "preset_saved": False
            }
        finally:
            frame_grabber.stop()

    def _log_execution(self, preset_data: dict, error: Optional[Any], elapsed_ms: int, result: str, error_msg: str = None):
        """실행 이력 DB 기록"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO autoset_logs (
                    camera_id, preset_id, base_preset_no, live_preset_no, target_mode,
                    detection_confidence, initial_x_error, initial_y_error, final_x_error, final_y_error,
                    elapsed_time_ms, result, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                preset_data["camera_id"], preset_data["id"], preset_data["base_preset_no"], preset_data["live_preset_no"],
                preset_data["target_mode"],
                error.confidence if error else 0.0,
                0.0, 0.0,
                error.x_error if error else 0.0,
                error.y_error if error else 0.0,
                elapsed_ms, result, error_msg
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to log autoset execution: {e}")

autoset_engine = AutoSetEngine()
