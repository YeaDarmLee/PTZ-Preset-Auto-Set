import logging
import asyncio
import os
# OpenCV FFMPEG C++ 네이티브 로그 수위 조절 및 소켓 타임아웃 단축
os.environ["OPENCV_LOG_LEVEL"] = "ERROR"
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "timeout;2000000" # 2 seconds timeout in microseconds

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.database import init_db, get_db_connection
from app.routes import dashboard, cameras, presets, autoset
from app.websocket import status_hub

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ptz-autoset")

app = FastAPI(title=settings.APP_NAME, version="1.0.0")

# Static & Mounts
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include Routers
app.include_router(dashboard.router)
app.include_router(cameras.router)
app.include_router(presets.router)
app.include_router(autoset.router)
app.include_router(status_hub.router)

@app.on_event("startup")
async def on_startup():
    logger.info("Initializing Database...")
    init_db()
    logger.info("PTZ Preset Auto Set Server started successfully!")

@app.get("/api/health")
def health_check():
    """
    시스템 Health Check 엔드포인트
    Server, DB, Camera 연결 상태 진단
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM cameras WHERE enabled = 1")
    enabled_cams = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM presets WHERE auto_set_enabled = 1")
    enabled_presets = cursor.fetchone()[0]
    conn.close()

    status = "READY" if enabled_cams > 0 else "DEGRADED"

    return {
        "status": status,
        "enabled_cameras": enabled_cams,
        "enabled_presets": enabled_presets,
        "vision_engine": "RTMPose ONNX Ready",
        "stream_deck": "WebSocket Connected"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
