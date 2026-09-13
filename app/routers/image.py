"""
图片生成路由
"""
import os
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.task import (
    APIResponse,
    ImageGenerationRequest,
    TaskResponse,
    FileUploadResponse
)
from app.services.image_service import ImageService
from app.utils.file_utils import upload_file_helper
from app.utils.credits import check_and_deduct_credits
from app.data.prices import IMAGE_COST
from app.rq_app import queue_image
from app.tasks.image_tasks import generate_image_task

router = APIRouter(prefix="/image", tags=["图片生成"])

# ========== 是否使用异步模式 ==========
USE_ASYNC = os.getenv("USE_ASYNC", "false").lower() == "true"
print(f"[IMAGE] USE_ASYNC = {USE_ASYNC}")
# =====================================


@router.post("/generate", response_model=APIResponse)
async def generate_image(
    prompt: str = Form(...),
    negative_prompt: Optional[str] = Form(None),
    width: int = Form(512),
    height: int = Form(512),
    num_images: int = Form(1),
    reference_image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    生成图片
    """
    # ========== 1. 处理参考图上传 ==========
    reference_image_url = None
    reference_image_id = None
    
    if reference_image:
        file_url, file_id = await upload_file_helper(reference_image, "reference")
        reference_image_url = file_url
        reference_image_id = file_id
        print(f"[DEBUG] 参考图已上传到 OSS: {reference_image_url}")
    else:
        print(f"[DEBUG] 未提供参考图")

    # ========== 2. 构建请求数据 ==========
    request_data = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "num_images": num_images,
        "reference_image_id": reference_image_id,
        "reference_image_url": reference_image_url
    }
    
    print(f"[DEBUG] 图片生成请求 - prompt: {prompt[:50]}...")
    
    cost = IMAGE_COST
    user = current_user
    user_id = current_user.id

    # ========== 3. 判断模式 ==========
    if USE_ASYNC:
        # ========== 异步模式 ==========
        print(f"[IMAGE] 使用异步模式")
        
        # 检查队列是否可用
        if queue_image is None:
            raise HTTPException(status_code=500, detail="异步队列未初始化，请检查Redis连接")
        
        # 先扣费（失败抛异常，不创建任务）
        check_and_deduct_credits(user, db, cost, "图片生成")
        
        # 创建任务
        from app.models.task import Task
        task = Task(
            user_id=user_id,
            task_type="image_gen",
            status="pending",
            input_data=request_data,
            credits_cost=cost,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        # 提交到队列
        job = queue_image.enqueue(generate_image_task, task.id, user_id, request_data)
        print(f"[IMAGE] RQ 任务已提交: task_id={task.id}, job_id={job.id}")
        
        return APIResponse(
            code=200,
            message="图片生成任务已提交，预计30秒内完成",
            data={
                "task_id": task.id,
                "status": "pending",
                "async": True
            }
        )
    else:
        # ========== 同步模式（原有逻辑） ==========
        print(f"[IMAGE] 使用同步模式")
        
        # 生成前检查余额（不扣除）
        if user.credits < cost:
            raise HTTPException(status_code=403, detail=f"图片生成需要{cost}灵境点，当前余额不足，请充值")
        
        # 调用生成服务
        task = await ImageService.generate_image(db, user_id, request_data)
        
        if task.status != "completed":
            raise HTTPException(500, detail=task.error_message or "图片生成失败")
        
        # 生成成功后扣点
        check_and_deduct_credits(user, db, cost, "图片生成")
        
        print(f"[DEBUG] 返回给前端的 output_data: {task.output_data}")
        return APIResponse(
            code=200,
            message="图片生成成功",
            data=TaskResponse.model_validate(task)
        )


@router.get("/task/{task_id}", response_model=APIResponse)
def get_image_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取图片生成任务状态
    """
    task = ImageService.get_task_result(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 验证任务所属
    if task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")

    return APIResponse(
        code=200,
        message="获取成功",
        data=TaskResponse.model_validate(task)
    )