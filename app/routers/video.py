"""
视频生成路由
"""
import base64
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.schemas.task import APIResponse, TaskResponse
from app.services.video_service import VideoService
from app.config import settings
from app.models.user import User
from app.utils.file_utils import upload_file_helper  # 新增：导入 OSS 上传工具

router = APIRouter(prefix="/video", tags=["视频生成"])


@router.post("/generate", response_model=APIResponse)
async def generate_video(
    image: UploadFile = File(...),
    prompt: Optional[str] = Form(""),
    duration: int = Form(5),
    mode: str = Form("std"),
    db: Session = Depends(get_db),
):
    """
    图生视频
    """
    # ========== 1. 上传用户图片到 OSS ==========
    # 将用户上传的图片保存到 OSS，获取公网 URL
    image_url, image_id = await upload_file_helper(image, "video")
    print(f"[DEBUG] 用户图片已上传到 OSS: {image_url}")
    # ========== OSS 上传结束 ==========
    
    # ========== 2. 构建请求数据 ==========
    request_data = {
        "image_url": image_url,  # 使用 OSS URL
        "prompt": prompt,
        "duration": duration,
        "mode": mode
    }
    
    # ========== 3. 用户 ID（临时固定） ==========
    user_id = 1
    
    # ========== 4. 确保用户存在 ==========
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        from datetime import datetime
        user = User(
            id=user_id,
            phone=f"temp_{user_id}@example.com",
            username=f"user_{user_id}",
            password_hash="auto_created_temp_hash"
        )
        db.add(user)
        db.commit()
        print(f"[DEBUG] 自动创建了用户: id={user.id}")
    
    # ========== 5. 调用视频生成服务 ==========
    task = await VideoService.generate_video(db, user_id, request_data)
    
    return APIResponse(
        code=200,
        message="视频生成任务已提交",
        data=TaskResponse.model_validate(task)
    )


@router.get("/task/{task_id}", response_model=APIResponse)
def get_video_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    """获取视频生成任务状态"""
    task = VideoService.get_task_result(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return APIResponse(
        code=200,
        message="获取成功",
        data=TaskResponse.model_validate(task)
    )