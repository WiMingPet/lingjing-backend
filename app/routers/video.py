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
from app.models.user import User  # ← 新增这一行导入

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
    # 临时使用公网测试图片
    image_url = "https://picsum.photos/id/104/512/512"
    print(f"[DEBUG] 使用测试图片 URL: {image_url}")
    
    request_data = {
        "image_url": image_url,
        "prompt": prompt,
        "duration": duration,
        "mode": mode
    }
    
    user_id = 1
    
    # 确保用户存在，如果不存在则自动创建
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
    # ========== 新增代码结束 ==========
    
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