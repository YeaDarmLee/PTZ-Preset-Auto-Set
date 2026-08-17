import time
import threading
import logging
from typing import Optional, Tuple
import cv2
import numpy as np

logger = logging.getLogger(__name__)

class FrameGrabber:
    """
    RTSP IP 카메라 영상 스팀 수신기
    - 최신 프레임 단일 버퍼링 (Buffer Latency 제거)
    - 백그라운드 스레드 캡처
    - Timestamp / Frame Generation 관리
    - PTZ 이동 직후 버퍼 플러싱(Flush) 지원
    """

    def __init__(self, rtsp_url: str, reconnect_interval: float = 3.0):
        self.rtsp_url = rtsp_url
        self.reconnect_interval = reconnect_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cap: Optional[cv2.VideoCapture] = None

        self._latest_frame: Optional[np.ndarray] = None
        self._latest_timestamp: float = 0.0
        self._frame_generation: int = 0
        self._lock = threading.Lock()

    def start(self):
        """캡처 스레드 시작"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._grab_loop, daemon=True)
        self._thread.start()
        logger.info(f"FrameGrabber started for {self.rtsp_url}")

    def stop(self):
        """캡처 스레드 중지"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._cap:
            self._cap.release()
            self._cap = None
        logger.info(f"FrameGrabber stopped for {self.rtsp_url}")

    def flush_buffer(self):
        """
        PTZ 이동 직후 디코더 버퍼에 남아있는 과거 프레임을 즉시 비우고 
        Generation Token을 증가시킴
        """
        with self._lock:
            self._latest_frame = None
            self._latest_timestamp = time.time()
            self._frame_generation += 1
        logger.debug(f"FrameGrabber buffer flushed (generation={self._frame_generation})")

    def get_latest_frame(self) -> Tuple[Optional[np.ndarray], float, int]:
        """
        최신 프레임, Timestamp, Frame Generation 반환
        Returns:
            (frame, timestamp, generation)
        """
        with self._lock:
            if self._latest_frame is None:
                return None, 0.0, self._frame_generation
            return self._latest_frame.copy(), self._latest_timestamp, self._frame_generation

    def _grab_loop(self):
        while self._running:
            if self._cap is None or not self._cap.isOpened():
                logger.info(f"Connecting to RTSP Stream: {self.rtsp_url}")
                # FFmpeg RTSP low latency option set via OpenCV
                self._cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # Buffer size = 1
                if not self._cap.isOpened():
                    logger.warning(f"RTSP connection failed. Retrying in {self.reconnect_interval}s...")
                    time.sleep(self.reconnect_interval)
                    continue

            ret, frame = self._cap.read()
            if not ret or frame is None:
                logger.warning("Failed to grab RTSP frame. Reconnecting...")
                self._cap.release()
                self._cap = None
                time.sleep(1.0)
                continue

            # 최신 프레임 갱신 (지연 없이 최신 것만 보관)
            now = time.time()
            with self._lock:
                self._latest_frame = frame
                self._latest_timestamp = now
