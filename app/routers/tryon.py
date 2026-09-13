"""
虚拟试穿路由
"""
import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from app.database import get_db
from app.schemas.task import APIResponse, TaskResponse
from app.services.tryon_service import TryonService
from app.models.user import User
from app.utils.file_utils import upload_file_helper
from app.utils.credits import check_and_deduct_credits
from app.utils.auth import get_current_user
from app.data.prices import TRYON_COST
from app.rq_app import queue_other
from app.tasks.other_tasks import generate_tryon_task

router = APIRouter(prefix="/tryon", tags=["虚拟试穿"])

# ========== 是否使用异步模式 ==========
USE_ASYNC = os.getenv("USE_ASYNC", "false").lower() == "true"
print(f"[TRYON] USE_ASYNC = {USE_ASYNC}")
# =====================================


# ========== 可选认证依赖 ==========
async def get_current_user_optional(
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """可选的用户认证（内部调用时不需要 token）"""
    if authorization:
        try:
            token = authorization.replace("Bearer ", "")
            return await get_current_user(db=db, token=token)
        except:
            pass
    return None


@router.post("/generate", response_model=APIResponse)
async def generate_tryon(
    model_image: UploadFile = File(...),
    garment_image: UploadFile = File(...),
    digital_human_id: Optional[int] = Form(None),
    title: Optional[str] = Form(None),
    cloth_category: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """虚拟试穿"""
    # ========== 上传用户图片到 OSS ==========
    model_image_url, model_image_id = await upload_file_helper(model_image, "tryon/model")
    print(f"[DEBUG] 模特图片已上传到 OSS: {model_image_url}")
    
    garment_image_url, garment_image_id = await upload_file_helper(garment_image, "tryon/garment")
    print(f"[DEBUG] 服装图片已上传到 OSS: {garment_image_url}")
    
    request_data = {
        "model_image_url": model_image_url,
        "garment_image_url": garment_image_url,
        "digital_human_id": digital_human_id,
        "title": title or "",
        "cloth_category": cloth_category or ""
    }
    
    user = current_user
    user_id = current_user.id
    cost = TRYON_COST
    
    # ========== 判断模式 ==========
    if USE_ASYNC:
        # ========== 异步模式 ==========
        print(f"[TRYON] 使用异步模式")
        
        if queue_other is None:
            raise HTTPException(status_code=500, detail="异步队列未初始化，请检查Redis连接")
        
        # 先扣费
        check_and_deduct_credits(user, db, cost, "虚拟试穿")
        
        # 创建任务
        from app.models.task import Task
        task = Task(
            user_id=user_id,
            task_type="tryon",
            status="pending",
            input_data=request_data,
            credits_cost=cost,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        # 提交队列
        job = queue_other.enqueue(generate_tryon_task, task.id, user_id, request_data)
        print(f"[TRYON] RQ 任务已提交: task_id={task.id}, job_id={job.id}")
        
        return APIResponse(
            code=200,
            message="虚拟试穿任务已提交，预计1分钟内完成",
            data={
                "task_id": task.id,
                "status": "pending",
                "async": True
            }
        )
    else:
        # ========== 同步模式（原有逻辑） ==========
        print(f"[TRYON] 使用同步模式")
        
        # 生成前检查余额
        if user.credits < cost:
            raise HTTPException(status_code=403, detail=f"虚拟试穿需要{cost}灵境点，当前余额不足，请充值")
        
        # 调用生成服务
        task = await TryonService.generate_tryon(db, user_id, request_data)
        
        if task.status != "completed":
            raise HTTPException(500, detail=task.error_message or "虚拟试穿失败")
        
        # 生成成功后扣费
        check_and_deduct_credits(user, db, cost, "虚拟试穿")
        
        return APIResponse(
            code=200,
            message="虚拟试穿任务已提交",
            data=TaskResponse.model_validate(task)
        )


@router.get("/task/{task_id}", response_model=APIResponse)
def get_tryon_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    """获取虚拟试穿任务状态"""
    task = TryonService.get_task_result(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return APIResponse(
        code=200,
        message="获取成功",
        data=TaskResponse.model_validate(task)
    )


# ========== 通过URL生成试穿（服务器内部专用） ==========
class TryonByUrlRequest(BaseModel):
    model_image_url: str
    garment_image_url: str


@router.post("/generate_by_url", response_model=APIResponse)
async def generate_tryon_by_url(
    request: TryonByUrlRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_optional),
    x_internal_key: str = Header(None, alias="X-Internal-Key")
):
    """通过图片URL生成虚拟试穿（服务器内部专用）"""
    # 安全校验
    INTERNAL_KEY = os.getenv("INTERNAL_API_KEY", "lingjing-internal-2026")
    if x_internal_key != INTERNAL_KEY:
        raise HTTPException(status_code=403, detail="仅限内部调用")
    
    # 只有用户登录时才扣点（内部调用免扣点）
    if current_user:
        check_and_deduct_credits(current_user, db, TRYON_COST, "虚拟试穿")
    
    request_data = {
        "model_image_url": request.model_image_url,
        "garment_image_url": request.garment_image_url,
        "title": "",
        "cloth_category": ""
    }
    
    task = await TryonService.generate_tryon(
        db, 
        current_user.id if current_user else 1, 
        request_data
    )
    
    return APIResponse(
        code=200,
        message="虚拟试穿任务已提交",
        data=TaskResponse.model_validate(task)
    )