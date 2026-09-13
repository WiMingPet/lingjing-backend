"""
视频生成路由 - 支持同步和异步模式
"""
import os
import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.schemas.task import APIResponse, TaskResponse
from app.services.video_service import VideoService
from app.models.user import User
from app.utils.file_utils import upload_file_helper
from app.utils.credits import check_and_deduct_credits
from app.utils.auth import get_current_user
from app.data.prices import VIDEO_PRICES, get_video_cost
from app.rq_app import queue_video
from app.tasks.video_tasks import generate_video_task

router = APIRouter(prefix="/video", tags=["视频生成"])

# ========== 是否使用异步模式 ==========
USE_ASYNC = os.getenv("USE_ASYNC", "false").lower() == "true"
print(f"[VIDEO] USE_ASYNC = {USE_ASYNC}")
# =====================================


@router.post("/generate", response_model=APIResponse)
async def generate_video(
    image: UploadFile = File(...),
    prompt: Optional[str] = Form(""),
    duration: int = Form(5),
    mode: str = Form("std"),
    model: str = Form("2.6"),
    sound: str = Form("off"),
    credits: int = Form(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """图生视频 - 支持2.6基础版和3.0增强版"""
    
    # ========== 0. 参数验证 ==========
    if model not in ["2.6", "3.0"]:
        raise HTTPException(status_code=400, detail="无效的模型选择")
    
    if sound not in ["off", "native"]:
        raise HTTPException(status_code=400, detail="无效的声音模式")
    
    if model == "2.6":
        if sound != "off":
            raise HTTPException(status_code=400, detail="2.6基础版仅支持无声视频")
        if duration not in [5, 10]:
            raise HTTPException(status_code=400, detail="2.6基础版仅支持5秒或10秒")
    else:
        if duration not in [5, 10, 15]:
            raise HTTPException(status_code=400, detail="3.0增强版支持5秒、10秒或15秒")
    
    cost = get_video_cost(model, sound, duration)
    if not cost:
        raise HTTPException(status_code=400, detail="无效的时长选择")
    
    if credits > 0 and credits != cost:
        raise HTTPException(status_code=400, detail=f"扣费金额不正确，应为{cost}点")
    
    # ========== 1. 上传用户图片到 OSS ==========
    image_url, image_id = await upload_file_helper(image, "video")
    print(f"[DEBUG] 用户图片已上传到 OSS: {image_url}")
    
    # ========== 2. 构建请求数据 ==========
    request_data = {
        "image_url": image_url,
        "prompt": prompt,
        "duration": duration,
        "mode": mode,
        "model": model,
        "sound": sound
    }
    
    user_id = current_user.id
    user = current_user
    
    # ========== 3. 判断模式 ==========
    if USE_ASYNC:
        # ========== 异步模式 ==========
        print(f"[VIDEO] 使用异步模式")
        
        # 检查队列
        if queue_video is None:
            raise HTTPException(status_code=500, detail="异步队列未初始化，请检查Redis连接")
        
        # 先扣费（失败抛异常，不创建任务）
        check_and_deduct_credits(
            user, db, cost,
            f"{'3.0增强版' if model == '3.0' else '2.6基础版'}{duration}秒{'有声' if sound == 'native' else '无声'}视频生成"
        )
        
        # 创建任务
        from app.models.task import Task
        task = Task(
            user_id=user_id,
            task_type="video_gen",
            status="pending",
            input_data=request_data,
            credits_cost=cost,
            progress=0
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        # 提交队列
        job = queue_video.enqueue(generate_video_task, task.id, user_id, request_data)
        print(f"[VIDEO] RQ 任务已提交: task_id={task.id}, job_id={job.id}")
        
        return APIResponse(
            code=200,
            message="视频生成任务已提交，预计1-3分钟完成",
            data={
                "task_id": task.id,
                "status": "pending",
                "async": True
            }
        )
    else:
        # ========== 同步模式（原有逻辑） ==========
        print(f"[VIDEO] 使用同步模式")
        
        # 生成前检查余额
        if user.credits < cost:
            raise HTTPException(
                status_code=403,
                detail=f"{'3.0增强版' if model == '3.0' else '2.6基础版'}{duration}秒{'有声' if sound == 'native' else '无声'}视频需要{cost}灵境点，当前余额不足，请充值"
            )
        
        # 调用生成服务
        task = await VideoService.generate_video(db, user_id, request_data)
        
        if task.status != "completed":
            raise HTTPException(500, detail=task.error_message or "视频生成失败")
        
        # 生成成功后扣费
        check_and_deduct_credits(
            user, db, cost,
            f"{'3.0增强版' if model == '3.0' else '2.6基础版'}{duration}秒{'有声' if sound == 'native' else '无声'}视频生成"
        )
        
        # 保存历史记录
        from app.models.history import History
        
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