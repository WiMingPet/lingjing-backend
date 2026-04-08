from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ai_creative")
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # App
    APP_NAME: str = "AI Creative Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Third Party APIs
    KLING_API_KEY: str = ""
    KLING_API_SECRET: str = ""
    KLING_API_URL: str = "https://api-beijing.klingai.com/v1"

    # OSS 配置
    OSS_ACCESS_KEY_ID: str = ""
    OSS_ACCESS_KEY_SECRET: str = ""
    OSS_BUCKET_NAME: str = "lingjing-media"
    OSS_ENDPOINT: str = "oss-cn-shenzhen.aliyuncs.com"
    OSS_INTERNAL_ENDPOINT: str = "oss-cn-shenzhen-internal.aliyuncs.com"

    # File Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE: int = 10485760
    ALLOWED_IMAGE_EXTENSIONS: List[str] = ["jpg", "jpeg", "png", "webp"]
    ALLOWED_VIDEO_EXTENSIONS: List[str] = ["mp4", "avi", "mov"]

    # Task Queue
    RQ_QUEUE_NAME: str = "default"
    
    # API Ninjas
    APININJAS_API_KEY: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

# Create upload directory if not exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
