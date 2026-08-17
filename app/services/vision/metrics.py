import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

@dataclass
class VisionPerformanceMetrics:
    inference_fps: float = 0.0
    inference_latency_ms: float = 0.0
    detection_confidence: float = 0.0
    keypoint_confidence: float = 0.0
    keypoint_jitter: float = 0.0
    rtsp_latency_ms: float = 0.0

class VisionMetricsCollector:
    """
    Vision Engine의 실시간 성능 및 좌표 흔들림(Jitter) 측정기
    """

    def __init__(self):
        self._latencies: List[float] = []
        self._last_time = time.time()

    def record_inference(self, latency_ms: float, conf: float):
        now = time.time()
        dt = now - self._last_time
        self._last_time = now

        fps = 1.0 / dt if dt > 0 else 0.0
        self._latencies.append(latency_ms)
        if len(self._latencies) > 30:
            self._latencies.pop(0)

        avg_latency = sum(self._latencies) / len(self._latencies)
        logger.debug(f"[Vision Metrics] FPS: {fps:.1f} | Avg Latency: {avg_latency:.1f}ms | Conf: {conf:.2f}")

    def get_current_metrics(self) -> Dict[str, Any]:
        return {
            "fps": round(1.0 / (sum(self._latencies)/len(self._latencies)*0.001) if self._latencies else 0.0, 1),
            "avg_latency_ms": round(sum(self._latencies)/len(self._latencies) if self._latencies else 0.0, 1)
        }
