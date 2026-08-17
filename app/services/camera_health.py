import time
import socket
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
import cv2
from app.services.state_manager import HealthStatus, state_manager

logger = logging.getLogger(__name__)

@dataclass
class HealthCheckResult:
    success: bool
    visca_status: HealthStatus
    visca_latency_ms: Optional[float]
    visca_error: Optional[str]
    rtsp_status: HealthStatus
    rtsp_resolution: Optional[str]
    rtsp_error: Optional[str]

class CameraHealthService:
    """
    VISCA (소켓/Inquiry) 및 RTSP (1-Frame Grab & Resolution) 분리 헬스 체크 서비스
    """

    def __init__(
        self,
        visca_timeout_sec: float = 1.0,
        rtsp_open_timeout_sec: float = 3.0,
        rtsp_frame_timeout_sec: float = 3.0
    ):
        self.visca_timeout_sec = visca_timeout_sec
        self.rtsp_open_timeout_sec = rtsp_open_timeout_sec
        self.rtsp_frame_timeout_sec = rtsp_frame_timeout_sec

    @staticmethod
    def mask_rtsp_url(rtsp_url: str) -> str:
        """RTSP URL 비밀번호 마스킹 (e.g. rtsp://user:pass@192.168.1.1/ -> rtsp://***:***@192.168.1.1/)"""
        if not rtsp_url or "@" not in rtsp_url:
            return rtsp_url
        try:
            proto, rest = rtsp_url.split("://", 1)
            credentials, host_path = rest.split("@", 1)
            return f"{proto}://***:***@{host_path}"
        except Exception:
            return "rtsp://***:***@masked"

    @staticmethod
    def build_full_rtsp_url(rtsp_url: str, username: Optional[str] = None, password: Optional[str] = None) -> str:
        """Username/Password가 존재할 경우 RTSP URL에 인라인 구성"""
        if not username or not password or "@" in rtsp_url:
            return rtsp_url
        try:
            proto, host_path = rtsp_url.split("://", 1)
            return f"{proto}://{username}:{password}@{host_path}"
        except Exception:
            return rtsp_url

    async def test_visca(self, ip: str, port: int = 52381, protocol: str = "UDP") -> Tuple[HealthStatus, Optional[float], Optional[str]]:
        """
        VISCA 헬스 체크:
        - TCP: 소켓 핸드셰이크
        - UDP: Inquiry 패킷 (81 09 00 02 FF) 송신 및 수신 확인
        """
        t0 = time.time()
        loop = asyncio.get_running_loop()
        proto_upper = protocol.upper()

        try:
            if proto_upper == "TCP":
                fut = asyncio.open_connection(ip, port)
                reader, writer = await asyncio.wait_for(fut, timeout=self.visca_timeout_sec)
                writer.close()
                await writer.wait_closed()
                latency = round((time.time() - t0) * 1000, 1)
                return HealthStatus.CONNECTED, latency, None

            else:  # UDP
                def _udp_inquiry():
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.settimeout(self.visca_timeout_sec)
                    # VISCA IP Inquiry Packet Header + Payload
                    # Header: 01 10 (Inquiry) 00 05 (len) 00 00 00 01 (seq) + 81 09 00 02 FF
                    pkt = b"\x01\x10\x00\x05\x00\x00\x00\x01\x81\x09\x00\x02\xFF"
                    sock.sendto(pkt, (ip, port))
                    data, _ = sock.recvfrom(1024)
                    sock.close()
                    return data

                await loop.run_in_executor(None, _udp_inquiry)
                latency = round((time.time() - t0) * 1000, 1)
                return HealthStatus.CONNECTED, latency, None

        except asyncio.TimeoutError:
            return HealthStatus.FAILED, None, "VISCA Connection Timeout"
        except Exception as e:
            return HealthStatus.FAILED, None, f"VISCA Error: {str(e)}"

    async def test_rtsp(self, full_rtsp_url: str) -> Tuple[HealthStatus, Optional[str], Optional[str]]:
        """
        RTSP 헬스 체크:
        - RTSP Stream Open
        - 1-Frame Grab 및 Resolution (Width x Height) 측정
        """
        loop = asyncio.get_running_loop()

        def _rtsp_grab():
            cap = cv2.VideoCapture(full_rtsp_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not cap.isOpened():
                cap.release()
                return False, None, "Failed to open RTSP stream"

            ret, frame = cap.read()
            if not ret or frame is None:
                cap.release()
                return False, None, "Failed to grab frame from RTSP stream"

            h, w = frame.shape[:2]
            resolution = f"{w}x{h}"
            cap.release()
            return True, resolution, None

        try:
            success, res, err = await asyncio.wait_for(
                loop.run_in_executor(None, _rtsp_grab),
                timeout=self.rtsp_open_timeout_sec + self.rtsp_frame_timeout_sec
            )
            if success:
                return HealthStatus.CONNECTED, res, None
            else:
                return HealthStatus.FAILED, None, err
        except asyncio.TimeoutError:
            return HealthStatus.FAILED, None, "RTSP Frame Grab Timeout"
        except Exception as e:
            return HealthStatus.FAILED, None, f"RTSP Error: {str(e)}"

    async def test_draft_connection(
        self,
        ip: str,
        visca_port: int,
        visca_protocol: str,
        rtsp_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None
    ) -> HealthCheckResult:
        """저장 전 Draft 설정에 대한 2단계 분리 헬스 체크"""
        full_rtsp = self.build_full_rtsp_url(rtsp_url, username, password)

        try:
            visca_status, latency, visca_err = await self.test_visca(ip, visca_port, visca_protocol)
        except Exception as e:
            visca_status, latency, visca_err = HealthStatus.FAILED, None, f"VISCA Error: {str(e)}"

        try:
            rtsp_status, res, rtsp_err = await self.test_rtsp(full_rtsp)
        except Exception as e:
            rtsp_status, res, rtsp_err = HealthStatus.FAILED, None, f"RTSP Error: {str(e)}"

        overall_success = (visca_status == HealthStatus.CONNECTED) and (rtsp_status == HealthStatus.CONNECTED)

        return HealthCheckResult(
            success=overall_success,
            visca_status=visca_status,
            visca_latency_ms=latency,
            visca_error=visca_err,
            rtsp_status=rtsp_status,
            rtsp_resolution=res,
            rtsp_error=rtsp_err
        )

camera_health_service = CameraHealthService()
