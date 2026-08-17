import logging
import numpy as np
from typing import List, Optional, Tuple
from app.services.vision.base_detector import PoseDetectorBase, PoseResult

logger = logging.getLogger(__name__)

class RTMLibPoseDetector(PoseDetectorBase):
    """
    Tau-J/rtmlib (RTMPose + ONNX Runtime) 기반 Pose Detector 구현체
    """

    def __init__(self):
        self.device = "cpu"
        self.model_size = "m"
        self.body_tracker = None
        self._initialized = False

    def initialize(self, model_size: str = "m", device: str = "cpu") -> bool:
        self.model_size = model_size
        self.device = device
        try:
            import rtmlib
            # rtmlib.Body 래퍼 이용
            self.body_tracker = rtmlib.Body(
                to_openpose=False,
                mode=self.model_size,  # 'lightweight', 'balanced', 'performance' or 's', 'm', 'l'
                backend='onnxruntime',
                device=self.device
            )
            self._initialized = True
            logger.info(f"RTMLibPoseDetector initialized successfully (mode={self.model_size}, device={self.device})")
            return True
        except ImportError:
            logger.warning("rtmlib is not installed in environment. Fallback/Mock mode active.")
            self._initialized = False
            return False
        except Exception as e:
            logger.error(f"Failed to initialize RTMLibPoseDetector: {e}")
            self._initialized = False
            return False

    def detect(self, frame: np.ndarray, roi: Optional[Tuple[float, float, float, float]] = None) -> List[PoseResult]:
        """
        frame: OpenCV BGR Image (H, W, C)
        roi: (roi_x1, roi_y1, roi_x2, roi_y2) Normalized (0.0 ~ 1.0)
        """
        if frame is None or frame.size == 0:
            return []

        h, w = frame.shape[:2]

        # ROI Crop 및 Coordinates offset 계산
        if roi:
            rx1, ry1, rx2, ry2 = roi
            x1_px, y1_px = int(rx1 * w), int(ry1 * h)
            x2_px, y2_px = int(rx2 * w), int(ry2 * h)
            
            # 클리핑
            x1_px, y1_px = max(0, x1_px), max(0, y1_px)
            x2_px, y2_px = min(w, x2_px), min(h, y2_px)

            if x2_px <= x1_px or y2_px <= y1_px:
                return []

            crop_img = frame[y1_px:y2_px, x1_px:x2_px]
            crop_w = x2_px - x1_px
            crop_h = y2_px - y1_px
        else:
            rx1, ry1 = 0.0, 0.0
            crop_img = frame
            crop_w, crop_h = w, h

        results: List[PoseResult] = []

        if self._initialized and self.body_tracker:
            try:
                keypoints, scores = self.body_tracker(crop_img)
                # keypoints: (N_persons, 17, 2) in crop pixel coordinates
                # scores: (N_persons, 17)
                if keypoints is not None and len(keypoints) > 0:
                    for i in range(len(keypoints)):
                        kps_local = keypoints[i]
                        kps_scores = scores[i]
                        
                        # Full-frame Normalized Coordinates (0.0 ~ 1.0) 로 변환
                        # X_full = rx1 + (X_crop / crop_w) * (rx2 - rx1)
                        norm_kps = np.zeros_like(kps_local, dtype=np.float32)
                        for k_idx in range(len(kps_local)):
                            kx_norm_crop = kps_local[k_idx][0] / max(1, crop_w)
                            ky_norm_crop = kps_local[k_idx][1] / max(1, crop_h)

                            norm_kps[k_idx][0] = rx1 + kx_norm_crop * (roi[2] - rx1 if roi else 1.0)
                            norm_kps[k_idx][1] = ry1 + ky_norm_crop * (roi[3] - ry1 if roi else 1.0)

                        # Bounding Box 계산 (Keypoints의 min/max)
                        valid_mask = kps_scores > 0.2
                        if np.any(valid_mask):
                            valid_kps = norm_kps[valid_mask]
                            bx1, by1 = float(np.min(valid_kps[:, 0])), float(np.min(valid_kps[:, 1]))
                            bx2, by2 = float(np.max(valid_kps[:, 0])), float(np.max(valid_kps[:, 1]))
                        else:
                            bx1, by1, bx2, by2 = rx1, ry1, roi[2] if roi else 1.0, roi[3] if roi else 1.0

                        bbox_score = float(np.mean(kps_scores[valid_mask])) if np.any(valid_mask) else 0.0

                        results.append(
                            PoseResult(
                                bbox=[bx1, by1, bx2, by2],
                                bbox_score=bbox_score,
                                keypoints=norm_kps,
                                keypoint_scores=kps_scores
                            )
                        )
            except Exception as e:
                logger.error(f"Error during RTMLib inference: {e}")

        return results
