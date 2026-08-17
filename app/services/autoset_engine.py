import time
import asyncio
import logging
from typing import Dict, Any, Optional
from app.database import get_db_connection
from app.services.camera_manager import camera_manager
from app.services.state_manager import state_manager
from app.services.ptz.motion_controller import MotionController
from app.services.vision.rtmlib_detector import RTMLibPoseDetector
from app.services.vision.vision_worker import VisionWorkerPool
from app.services.vision.frame_grabber import FrameGrabber
from app.services.vision.target_selector import TargetSelector, TargetMode
from app.services.vision.group_member_selector import GroupMemberSelector, PersonCountPolicy
from app.services.vision.group_calculator import GroupBBoxCalculator
from app.services.vision.stabilizer import TargetStabilizer
from app.services.vision.target_calculator import TargetCalculator, VerticalMetric, ScaleMetric

logger = logging.getLogger(__name__)

class AutoSetEngine:
    """
    Closed-Loop Auto Set 실행 엔진
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

        # DB에서 Preset 및 Camera 데이터 읽기
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

        preset_data = dict(row)
        camera_id = preset_data["camera_id"]
        base_no = preset_data["base_preset_no"]
        live_no = preset_data["live_preset_no"]

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

            motion_controller = MotionController(ptz)
            motion_controller.reset_accumulated_limits()

            # RTSP Frame Grabber 시작
            frame_grabber = FrameGrabber(preset_data["rtsp_url"])
            frame_grabber.start()

            try:
                # STEP 1: BASE Preset Recall
                logger.info(f"Recalling BASE Preset #{base_no} for '{preset_data['name']}'")
                await ptz.recall_preset(base_no)

                # STEP 2: Settle Time 대기 및 RTSP Buffer Flushing
                await asyncio.sleep(1.0)
                frame_grabber.flush_buffer()

                # 설정 및 헬퍼 초기화
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

                # STEP 3: Closed-Loop Adjustment Loop (최대 10회)
                success = False
                final_error = None
                max_iterations = 10

                for iteration in range(max_iterations):
                    if self._cancel_requested:
                        logger.warning("AutoSet execution cancelled by user!")
                        await state_manager.update_preset_status(camera_id, preset_id, "FAILED", "Cancelled")
                        return False

                    frame, ts, gen = frame_grabber.get_latest_frame()
                    if frame is None:
                        await asyncio.sleep(0.1)
                        continue

                    # Async Thread Pool Pose Detection
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
                        else:
                            logger.warning(f"Group Member Selection failed: {reason}")

                    if metrics_sample is None:
                        logger.warning(f"Iteration {iteration}: No valid target metrics sample found.")
                        await asyncio.sleep(0.2)
                        continue

                    # Multi-frame Stabilizer 샘플 추가
                    stable_metrics = stabilizer.add_sample(metrics_sample)
                    if stable_metrics is None:
                        # 아직 윈도우 수집 중
                        await asyncio.sleep(0.05)
                        continue

                    # 오차 계산
                    target_err = calculator.calculate_error(stable_metrics)
                    final_error = target_err

                    logger.info(
                        f"Iter {iteration} TargetError -> X: {target_err.x_error:.3f}, "
                        f"Y: {target_err.y_error:.3f}, Scale: {target_err.scale_error:.3f}"
                    )

                    # 수렴 조건 판정 (X, Y < ±3%, Scale < ±5%)
                    if (
                        abs(target_err.x_error) < 0.03 and
                        abs(target_err.y_error) < 0.03 and
                        abs(target_err.scale_error) < 0.05
                    ):
                        logger.info(f"Target successfully converged on iteration {iteration}!")
                        success = True
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

                    await asyncio.sleep(0.3)

                # STEP 4: 성공 여부 판정 및 LIVE Preset Save
                elapsed_ms = int((time.time() - start_time) * 1000)

                if success:
                    # 🚨 LIVE Preset SAVE (ProtectedPTZController 하드 가드 통과)
                    logger.info(f"Saving LIVE Preset #{live_no} for '{preset_data['name']}'")
                    await ptz.save_preset(live_no)

                    await state_manager.update_preset_status(camera_id, preset_id, "SUCCESS")
                    self._log_execution(preset_data, final_error, elapsed_ms, "SUCCESS")
                    return True
                else:
                    logger.warning(f"AutoSet FAILED for '{preset_data['name']}'. Preserving existing LIVE preset.")
                    await state_manager.update_preset_status(camera_id, preset_id, "FAILED", "Convergence Failed")
                    self._log_execution(preset_data, final_error, elapsed_ms, "FAILED", "Convergence or Limit Failed")
                    return False

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
