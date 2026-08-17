import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple
import numpy as np
from app.services.vision.base_detector import PoseDetectorBase, PoseResult

logger = logging.getLogger(__name__)

class VisionWorkerPool:
    """
    FastAPI Asyncio Event Loop의 블로킹(Blocking)을 방지하기 위해 
    별도의 Thread Pool에서 AI Inference를 수행하는 Vision Worker
    """

    def __init__(self, detector: PoseDetectorBase, max_workers: int = 2):
        self.detector = detector
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="VisionWorker")

    async def detect_async(
        self,
        frame: np.ndarray,
        roi: Optional[Tuple[float, float, float, float]] = None
    ) -> List[PoseResult]:
        """
        Non-blocking 비동기 Pose Detection 호출
        """
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(self.executor, self.detector.detect, frame, roi)
        except Exception as e:
            logger.error(f"VisionWorkerPool execution error: {e}")
            return []

    def shutdown(self):
        """Worker Pool 종료"""
        self.executor.shutdown(wait=False)
