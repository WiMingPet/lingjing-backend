from pydantic_settings import BaseSettings
from typing import List
import os



class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ai_creative")
    REDIS_URL: str = "redis://localhost:6379/0"
    # DashScope 通义千问
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "sk-42dfbcc5faf74e0ead60b1d415efd6f3")

    # JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # App
    APP_NAME: str = "AI Creative Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Third Party APIs
    KLING_API_KEY: str = os.getenv("KLING_API_KEY", "")
    KLING_API_SECRET: str = os.getenv("KLING_API_SECRET", "")
    KLING_API_URL: str = "https://api-beijing.klingai.com"
    

    # 腾讯云 TTS
    TENCENT_SECRET_ID: str = os.getenv("TENCENT_SECRET_ID", "")
    TENCENT_SECRET_KEY: str = os.getenv("TENCENT_SECRET_KEY", "")

    # OSS 配置
    OSS_ACCESS_KEY_ID: str = os.getenv("OSS_ACCESS_KEY_ID", "")
    OSS_ACCESS_KEY_SECRET: str = os.getenv("OSS_ACCESS_KEY_SECRET", "")
    OSS_BUCKET_NAME: str = "lingjing-media"
    OSS_ENDPOINT: str = "oss-cn-shenzhen.aliyuncs.com"
    OSS_PRIVATE_BUCKET_NAME: str = "lingjing-media-private"
    OSS_INTERNAL_ENDPOINT: str = "oss-cn-shenzhen-internal.aliyuncs.com"

    # 阿里云短信配置
    ALIBABA_CLOUD_ACCESS_KEY_ID: str = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
    ALIBABA_CLOUD_ACCESS_KEY_SECRET: str = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")
    SMS_SIGN_NAME: str = os.getenv("SMS_SIGN_NAME", "")
    SMS_TEMPLATE_CODE: str = os.getenv("SMS_TEMPLATE_CODE", "")

    # 微信支付
    WECHAT_MCHID: str = os.getenv("WECHAT_MCHID", "")
    WECHAT_APPID: str = os.getenv("WECHAT_APPID", "")
    WECHAT_APIV3_KEY: str = os.getenv("WECHAT_APIV3_KEY", "")
    WECHAT_CERT_SERIAL: str = os.getenv("WECHAT_CERT_SERIAL", "")
    WECHAT_PRIVATE_KEY: str = os.getenv("WECHAT_PRIVATE_KEY", "")
    WECHAT_PUBLIC_KEY: str = os.getenv("WECHAT_PUBLIC_KEY", "")
    WECHAT_PUBLIC_KEY_ID: str = os.getenv("WECHAT_PUBLIC_KEY_ID", "")
    WECHAT_APIV2_KEY: str = os.getenv("WECHAT_APIV2_KEY", "")
    
    # File Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE: int = 10485760
    ALLOWED_IMAGE_EXTENSIONS: List[str] = ["jpg", "jpeg", "png", "webp"]
    ALLOWED_VIDEO_EXTENSIONS: List[str] = ["mp4", "avi", "mov"]

    # Task Queue
    RQ_QUEUE_NAME: str = "default"
    
    # API Ninjas
    APININJAS_API_KEY: str = ""

    # IAP
    IAP_SHARED_SECRET: str = os.getenv("IAP_SHARED_SECRET", "")

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()

# Create upload directory if not exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

# OSS 自定义域名（用于生成可预览的 URL）
OSS_CUSTOM_DOMAIN = "https://media.lingjing-media.com"