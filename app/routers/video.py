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
from app.utils.file_utils import upload_file_helper
from app.utils.credits import check_and_deduct_credits
from app.utils.auth import get_current_user

router = APIRouter(prefix="/video", tags=["视频生成"])

# ========== 价格配置 ==========
VIDEO_PRICES = {
    '2.6': {
        'off': {5: 25, 10: 50}  # 2.6只支持5秒和10秒
    },
    '3.0': {
        'off': {5: 45, 10: 90, 15: 135},      # 3.0无声
        'native': {5: 60, 10: 120, 15: 180}   # 3.0有声
    }
}
# ==============================


@router.post("/generate", response_model=APIResponse)
async def generate_video(
    image: UploadFile = File(...),
    prompt: Optional[str] = Form(""),
    duration: int = Form(5),
    mode: str = Form("std"),
    model: str = Form("2.6"),      # 新增：模型选择
    sound: str = Form("off"),      # 新增：声音模式
    credits: int = Form(0),        # 新增：前端传入的扣费点数（用于校验）
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    图生视频 - 支持2.6基础版和3.0增强版
    """
    # ========== 0. 参数验证 ==========
    # 验证模型
    if model not in ["2.6", "3.0"]:
        raise HTTPException(status_code=400, detail="无效的模型选择")
    
    # 验证声音模式
    if sound not in ["off", "native"]:
        raise HTTPException(status_code=400, detail="无效的声音模式")
    
    # 2.6模型限制
    if model == "2.6":
        if sound != "off":
            raise HTTPException(status_code=400, detail="2.6基础版仅支持无声视频")
        if duration not in [5, 10]:
            raise HTTPException(status_code=400, detail="2.6基础版仅支持5秒或10秒")
    else:
        # 3.0模型限制
        if duration not in [5, 10, 15]:
            raise HTTPException(status_code=400, detail="3.0增强版支持5秒、10秒或15秒")
    
    # 计算正确的扣费点数
    expected_cost = VIDEO_PRICES[model][sound].get(duration)
    if not expected_cost:
        raise HTTPException(status_code=400, detail="无效的时长选择")
    
    # 如果前端传了credits，校验是否一致
    if credits > 0 and credits != expected_cost:
        raise HTTPException(status_code=400, detail=f"扣费金额不正确，应为{expected_cost}点")
    
    cost = expected_cost
    # ================================
    
    # ========== 1. 上传用户图片到 OSS ==========
    image_url, image_id = await upload_file_helper(image, "video")
    print(f"[DEBUG] 用户图片已上传到 OSS: {image_url}")
    
    # ========== 2. 构建请求数据 ==========
    request_data = {
        "image_url": image_url,
        "prompt": prompt,
        "duration": duration,
        "mode": mode,
        "model": model,        # 新增
        "sound": sound         # 新增
    }
    
    # ========== 3. 用户 ID ==========
    user_id = current_user.id
    user = current_user
    
    # ========== 4. 生成前检查余额 ==========
    if user.credits < cost:
        raise HTTPException(
            status_code=403, 
            detail=f"{'3.0增强版' if model == '3.0' else '2.6基础版'}{duration}秒{'有声' if sound == 'native' else '无声'}视频需要{cost}灵境点，当前余额不足，请充值"
        )
    
    # ========== 5. 调用视频生成服务 ==========
    task = await VideoService.generate_video(db, user_id, request_data)
    
    if task.status != "completed":
        raise HTTPException(500, detail=task.error_message or "视频生成失败")
    
    # ========== 6. 生成成功后扣点 ==========
    check_and_deduct_credits(user, db, cost, f"{model}模型{duration}秒{'有声' if sound == 'native' else '无声'}视频生成")
    
    # ========== 7. 保存历史记录 ==========
    from app.models.history import History
    import datetime
    
    # 生成封面图
    thumbnail_url = None
    try:
        thumbnail_url = await VideoService.extract_thumbnail(task.output_data["video_url"])
    except Exception as e:
        print(f"[DEBUG] 封面图生成失败: {e}")
    
    history = History(
        user_id=user_id,
        url=task.output_data["video_url"],
        type=f"视频生成-{model}{'有声' if sound == 'native' else '无声'}",
        thumbnail=thumbnail_url,
        created_at=datetime.datetime.utcnow()
    )
    db.add(history)
    db.commit()
    
    return APIResponse(
        code=200,
        message="视频生成成功",
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