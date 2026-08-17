import asyncio
import logging
from typing import Dict, Any
from app.services.ptz.visca import ViscaController
from app.services.ptz.guard import ProtectedPTZController

logger = logging.getLogger(__name__)

class ST20CapabilityProbe:
    """
    ST20 및 VISCA over IP 카메라의 물리 제어 특성(Capability) 자동 프로브
    - Preset Recall / Save
    - PTZ Relative Drive & Stop
    - Zoom Drive & Stop
    - Position Inquiry (Pan, Tilt, Zoom 레지스터)
    - Absolute Movement
    """

    def __init__(self, ip: str, port: int = 52381, protocol: str = "UDP"):
        self.raw_controller = ViscaController(ip=ip, port=port, protocol=protocol)
        # 안전을 위해 BASE 1~8번을 보호 목록으로 지정
        self.ptz = ProtectedPTZController(self.raw_controller, protected_base_presets={1, 2, 3, 4, 5, 6, 7, 8})

    async def run_probe(self) -> Dict[str, Any]:
        report: Dict[str, Any] = {
            "ip": self.raw_controller.ip,
            "port": self.raw_controller.port,
            "protocol": self.raw_controller.protocol,
            "capabilities": {}
        }

        logger.info(f"--- Starting Capability Probe for {self.raw_controller.ip}:{self.raw_controller.port} ---")
        
        # 1. Connection Test
        connected = await self.ptz.connect()
        report["capabilities"]["connection"] = connected
        if not connected:
            logger.error("Capability Probe aborted: Connection failed")
            return report

        # 2. Position Inquiry Test
        pos = await self.ptz.inquire_position()
        report["capabilities"]["position_inquiry"] = pos is not None
        report["capabilities"]["initial_position"] = pos
        logger.info(f"Position Inquiry Result: {pos}")

        # 3. PTZ Stop Test
        stop_ok = await self.ptz.stop()
        report["capabilities"]["stop"] = stop_ok

        # 4. Small Pan/Tilt Relative Movement & Stop Probe
        move_ok = await self.ptz.move_relative(pan_speed=3, tilt_speed=3, pan_dir="right", tilt_dir="stop")
        await asyncio.sleep(0.3)
        await self.ptz.stop()
        report["capabilities"]["relative_move"] = move_ok

        # 5. Base Save Guard Test (Safety Check)
        base_guard_triggered = False
        try:
            await self.ptz.save_preset(1) # BASE 1 저장 시도
        except PermissionError:
            base_guard_triggered = True
        report["capabilities"]["base_guard_working"] = base_guard_triggered
        logger.info(f"BASE Guard Test: {'PASSED (Blocked WRITE to BASE)' if base_guard_triggered else 'FAILED'}")

        # 6. Absolute Move Probe (If Position Inquiry is supported)
        if pos and "pan" in pos and "tilt" in pos:
            # 원래 위치로 absolute move 시도
            abs_ok = await self.ptz.move_absolute(pos["pan"], pos["tilt"], pan_speed=5, tilt_speed=5)
            report["capabilities"]["absolute_move"] = abs_ok
        else:
            report["capabilities"]["absolute_move"] = False

        await self.ptz.disconnect()
        logger.info(f"--- Capability Probe Complete --- Report: {report}")
        return report

async def main():
    import sys
    ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.101"
    probe = ST20CapabilityProbe(ip=ip)
    res = await probe.run_probe()
    print("Probe Result:", res)

if __name__ == "__main__":
    asyncio.run(main())
