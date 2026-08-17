import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "PTZ Preset Auto Set System"
    DEBUG: bool = True
    
    # Base Paths
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR: str = os.path.join(BASE_DIR, "data")
    DB_PATH: str = os.path.join(DATA_DIR, "autoset.db")
    LOG_DIR: str = os.path.join(BASE_DIR, "logs")

    # Host & Port
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Vision & PTZ Config
    DEFAULT_VISCA_PORT: int = 52381
    DEFAULT_RTSP_PORT: int = 554

    class Config:
        env_file = ".env"

settings = Settings()

# 디렉토리 자동 생성
os.makedirs(settings.DATA_DIR, exist_ok=True)
os.makedirs(settings.LOG_DIR, exist_ok=True)
