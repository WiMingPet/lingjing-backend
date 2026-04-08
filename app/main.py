"""
AI创意生成平台 - FastAPI应用入口
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.database import init_db, SessionLocal
from app.models.digital_human import DigitalHuman
from app.routers import auth, image, video, size, tryon, digital_human, multi_angle, proxy


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    print("Starting AI Creative Platform...")

    # 初始化数据库
    init_db()

    # 创建默认数字人
    db = SessionLocal()
    try:
        existing_default = db.query(DigitalHuman).filter(
            DigitalHuman.is_default == True
        ).first()

        if not existing_default:
            default_dh = DigitalHuman(
                merchant_id=None,
                name="默认数字人",
                description="系统默认数字人，用于用户未选择数字人时的试穿视频生成",
                source_video_url="https://example.com/default_digital_human.mp4",
                thumbnail_url="https://example.com/default_digital_human.jpg",
                is_default=True,
                is_active=True
            )
            db.add(default_dh)
            db.commit()
            print("Default digital human created.")
    finally:
        db.close()

    print("Application started successfully!")

    yield

    # 关闭时
    print("Shutting down AI Creative Platform...")


# 创建FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI创意生成平台 - 图片/视频生成、尺码推荐、多角度试穿、数字人定制",
    lifespan=lifespan
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
import os
os.makedirs("./uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="./uploads"), name="uploads")

# 注册路由（带 /api 前缀）
app.include_router(auth.router, prefix="/api")
app.include_router(image.router, prefix="/api")
app.include_router(video.router, prefix="/api")
app.include_router(size.router, prefix="/api")
app.include_router(tryon.router, prefix="/api")
app.include_router(digital_human.router, prefix="/api")
app.include_router(multi_angle.router, prefix="/api")


@app.get("/")
def root():
    """根路径"""
    return {
        "code": 200,
        "message": "欢迎使用AI创意生成平台",
        "data": {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": "/docs"
        }
    }


@app.get("/health")
def health_check():
    """健康检查"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)