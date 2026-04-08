"""
虚拟试穿路由
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.schemas.task import APIResponse, TaskResponse
from app.services.tryon_service import TryonService
from app.models.user import User
from app.utils.file_utils import upload_file_helper  # 新增：导入 OSS 上传工具

router = APIRouter(prefix="/tryon", tags=["虚拟试穿"])


@router.post("/generate", response_model=APIResponse)
async def generate_tryon(
    model_image: UploadFile = File(...),
    garment_image: UploadFile = File(...),
    digital_human_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    """
    虚拟试穿

    - **model_image**: 模特图片（必填）
    - **garment_image**: 服装图片（必填）
    - **digital_human_id**: 数字人ID（可选）
    """
    # ========== 上传用户图片到 OSS ==========
    # 上传模特图
    model_image_url, model_image_id = await upload_file_helper(model_image, "tryon/model")
    print(f"[DEBUG] 模特图片已上传到 OSS: {model_image_url}")
    
    # 上传服装图
    garment_image_url, garment_image_id = await upload_file_helper(garment_image, "tryon/garment")
    print(f"[DEBUG] 服装图片已上传到 OSS: {garment_image_url}")
    # ========== OSS 上传结束 ==========
    
    request_data = {
        "model_image_url": model_image_url,
        "garment_image_url": garment_image_url,
        "digital_human_id": digital_human_id
    }
    
    # 临时使用固定用户 ID 1
    user_id = 1
    
    # ========== 确保用户存在，如果不存在则自动创建 ==========
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
    
    task = await TryonService.generate_tryon(db, user_id, request_data)
    
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