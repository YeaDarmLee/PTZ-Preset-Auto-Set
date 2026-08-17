import asyncio
import socket
import logging
from typing import Optional, Dict, Any, Tuple
from app.services.ptz.base import PTZControllerBase

logger = logging.getLogger(__name__)

class ViscaController(PTZControllerBase):
    """
    VISCA over IP (UDP / TCP) 프로토콜 기반 PTZ 카메라 제어기
    Sony/Panasonic/Marshall/PTZOptics/ST20 등 VISCA 호환 네트워크 카메라 지원
    """

    def __init__(self, ip: str, port: int = 52381, protocol: str = "UDP", timeout: float = 3.0):
        self.ip = ip
        self.port = port
        self.protocol = protocol.upper()
        self.timeout = timeout
        self.sequence_number = 0
        self._connected = False
        self._transport = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    def _get_next_sequence_number(self) -> int:
        seq = self.sequence_number
        self.sequence_number = (self.sequence_number + 1) & 0xFFFFFFFF
        return seq

    def _build_visca_ip_packet(self, payload_type: bytes, visca_payload: bytes) -> bytes:
        """
        VISCA over IP 패킷 구성
        Header (8 bytes):
        - Payload Type (2 bytes): 0x01 0x00 (Command) 또는 0x01 0x10 (Inquiry)
        - Payload Length (2 bytes, Big-endian)
        - Sequence Number (4 bytes, Big-endian)
        """
        payload_len = len(visca_payload)
        seq_num = self._get_next_sequence_number()
        header = payload_type + payload_len.to_bytes(2, "big") + seq_num.to_bytes(4, "big")
        return header + visca_payload

    async def connect(self) -> bool:
        """소켓 연결 및 초기 세션 검증"""
        try:
            if self.protocol == "TCP":
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.ip, self.port), timeout=self.timeout
                )
            self._connected = True
            logger.info(f"VISCA Connected to {self.ip}:{self.port} via {self.protocol}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to VISCA camera {self.ip}:{self.port}: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """소켓 종료"""
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._connected = False
        logger.info(f"VISCA Disconnected from {self.ip}:{self.port}")

    async def _send_visca_command(self, visca_payload: bytes, is_inquiry: bool = False) -> Optional[bytes]:
        """VISCA 명령 또는 Inquiry 패킷 송신 및 수신"""
        payload_type = b"\x01\x10" if is_inquiry else b"\x01\x00"
        packet = self._build_visca_ip_packet(payload_type, visca_payload)

        try:
            if self.protocol == "TCP":
                if not self._writer:
                    if not await self.connect():
                        return None
                self._writer.write(packet)
                await self._writer.drain()
                
                # 수신 응답 읽기
                header = await asyncio.wait_for(self._reader.readexactly(8), timeout=self.timeout)
                resp_len = int.from_bytes(header[2:4], "big")
                resp_payload = await asyncio.wait_for(self._reader.readexactly(resp_len), timeout=self.timeout)
                return resp_payload

            else:  # UDP
                loop = asyncio.get_running_loop()
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(self.timeout)
                sock.sendto(packet, (self.ip, self.port))
                
                # UDP 수신 (비동기 소켓 수신)
                data, _ = await asyncio.wait_for(
                    loop.sock_recvfrom(sock, 1024), timeout=self.timeout
                )
                sock.close()
                if len(data) >= 8:
                    resp_len = int.from_bytes(data[2:4], "big")
                    return data[8:8 + resp_len]
                return None

        except Exception as e:
            logger.warning(f"VISCA comm error with {self.ip}:{self.port} - {e}")
            return None

    async def recall_preset(self, preset_no: int) -> bool:
        """
        Preset Recall: 81 01 04 3F 02 [preset_no] FF
        """
        p_no = max(0, min(255, preset_no))
        cmd = bytes([0x81, 0x01, 0x04, 0x3F, 0x02, p_no, 0xFF])
        resp = await self._send_visca_command(cmd)
        return resp is not None and (b"\x50" in resp or b"\x40" in resp)

    async def save_preset(self, preset_no: int) -> bool:
        """
        Preset Save (Set): 81 01 04 3F 01 [preset_no] FF
        주의: 본 메서드는 raw controller 수준으로 보호 레이어(ProtectedPTZController)에서 BASE 프리셋 번호를 필터링함.
        """
        p_no = max(0, min(255, preset_no))
        cmd = bytes([0x81, 0x01, 0x04, 0x3F, 0x01, p_no, 0xFF])
        resp = await self._send_visca_command(cmd)
        return resp is not None and (b"\x50" in resp or b"\x40" in resp)

    async def move_relative(self, pan_speed: int, tilt_speed: int, pan_dir: str, tilt_dir: str) -> bool:
        """
        Pan/Tilt Drive: 81 01 06 01 [pan_speed] [tilt_speed] [pan_dir] [tilt_dir] FF
        pan_dir: 'left' (01), 'right' (02), 'stop' (03)
        tilt_dir: 'up' (01), 'down' (02), 'stop' (03)
        pan_speed: 0x01 ~ 0x18 (1~24)
        tilt_speed: 0x01 ~ 0x14 (1~20)
        """
        p_spd = max(1, min(24, pan_speed))
        t_spd = max(1, min(20, tilt_speed))

        p_code = 0x01 if pan_dir == "left" else (0x02 if pan_dir == "right" else 0x03)
        t_code = 0x01 if tilt_dir == "up" else (0x02 if tilt_dir == "down" else 0x03)

        cmd = bytes([0x81, 0x01, 0x06, 0x01, p_spd, t_spd, p_code, t_code, 0xFF])
        resp = await self._send_visca_command(cmd)
        return resp is not None

    async def zoom_relative(self, zoom_speed: int, zoom_dir: str) -> bool:
        """
        Zoom Drive:
        tele: 81 01 04 07 2p FF
        wide: 81 01 04 07 3p FF
        stop: 81 01 04 07 00 FF
        """
        z_spd = max(0, min(7, zoom_speed))
        if zoom_dir == "tele":
            cmd = bytes([0x81, 0x01, 0x04, 0x07, 0x20 | z_spd, 0xFF])
        elif zoom_dir == "wide":
            cmd = bytes([0x81, 0x01, 0x04, 0x07, 0x30 | z_spd, 0xFF])
        else:
            cmd = bytes([0x81, 0x01, 0x04, 0x07, 0x00, 0xFF])

        resp = await self._send_visca_command(cmd)
        return resp is not None

    async def stop(self) -> bool:
        """모든 Pan/Tilt/Zoom 구동 정지"""
        pt_stop = await self.move_relative(1, 1, "stop", "stop")
        z_stop = await self.zoom_relative(0, "stop")
        return pt_stop and z_stop

    async def inquire_position(self) -> Optional[Dict[str, int]]:
        """
        Pan/Tilt/Zoom 위치 레지스터 Inquiry
        Pan/Tilt Inquiry: 81 09 06 12 FF
        Zoom Inquiry: 81 09 04 47 FF
        """
        pt_cmd = bytes([0x81, 0x09, 0x06, 0x12, 0xFF])
        pt_resp = await self._send_visca_command(pt_cmd, is_inquiry=True)

        z_cmd = bytes([0x81, 0x09, 0x04, 0x47, 0xFF])
        z_resp = await self._send_visca_command(z_cmd, is_inquiry=True)

        result = {}
        if pt_resp and len(pt_resp) >= 11 and pt_resp[0] == 0x90 and pt_resp[1] == 0x50:
            # 90 50 0p 0p 0p 0p 0t 0t 0t 0t FF
            pan = (pt_resp[2] & 0x0F) << 12 | (pt_resp[3] & 0x0F) << 8 | (pt_resp[4] & 0x0F) << 4 | (pt_resp[5] & 0x0F)
            tilt = (pt_resp[6] & 0x0F) << 12 | (pt_resp[7] & 0x0F) << 8 | (pt_resp[8] & 0x0F) << 4 | (pt_resp[9] & 0x0F)
            # signed 16-bit conversion
            if pan & 0x8000:
                pan -= 0x10000
            if tilt & 0x8000:
                tilt -= 0x10000
            result["pan"] = pan
            result["tilt"] = tilt

        if z_resp and len(z_resp) >= 7 and z_resp[0] == 0x90 and z_resp[1] == 0x50:
            # 90 50 0z 0z 0z 0z FF
            zoom = (z_resp[2] & 0x0F) << 12 | (z_resp[3] & 0x0F) << 8 | (z_resp[4] & 0x0F) << 4 | (z_resp[5] & 0x0F)
            result["zoom"] = zoom

        return result if result else None

    async def move_absolute(self, pan_pos: int, tilt_pos: int, pan_speed: int = 10, tilt_speed: int = 10) -> bool:
        """
        Absolute Pan/Tilt Move:
        81 01 06 02 VV WW Y1 Y2 Y3 Y4 Z1 Z2 Z3 Z4 FF
        """
        p_spd = max(1, min(24, pan_speed))
        t_spd = max(1, min(20, tilt_speed))

        p_hex = f"{(pan_pos & 0xFFFF):04X}"
        t_hex = f"{(tilt_pos & 0xFFFF):04X}"

        cmd = bytes([
            0x81, 0x01, 0x06, 0x02, p_spd, t_spd,
            int(p_hex[0], 16), int(p_hex[1], 16), int(p_hex[2], 16), int(p_hex[3], 16),
            int(t_hex[0], 16), int(t_hex[1], 16), int(t_hex[2], 16), int(t_hex[3], 16),
            0xFF
        ])
        resp = await self._send_visca_command(cmd)
        return resp is not None and (b"\x50" in resp or b"\x40" in resp)
