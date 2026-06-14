"""
尺码推荐路由
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional
import tempfile
import os
from app.database import get_db
from app.schemas.task import APIResponse, TaskResponse
from app.services.size_service import SizeService
from app.models.user import User
from app.utils.file_utils import upload_file_helper
from app.utils.credits import check_and_deduct_credits
from app.utils.auth import get_current_user  # ✅ 添加这一行

router = APIRouter(prefix="/size", tags=["尺码推荐"])


@router.post("/recommend", response_model=APIResponse)
async def recommend_size(
    image: UploadFile = File(...),
    height: Optional[float] = Form(170.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    image_url, image_id = await upload_file_helper(image, "size")
    content = await image.read()
    
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
        f.write(content)
        image_path = f.name
    
    try:
        user = current_user  # 用当前登录用户
        
        if user.credits < 2:
            raise HTTPException(status_code=403, detail="尺码推荐需要2灵境点，当前余额不足，请充值")
        task = await SizeService.recommend_size(db, user.id, image_path, height, image_url)
        
        if task.status != "completed":
            raise HTTPException(500, detail=task.error_message or "尺码推荐失败")
        
        check_and_deduct_credits(user, db, 2, "尺码推荐")
        
        return APIResponse(
            code=200,
            message="尺码推荐任务已提交",
            data=TaskResponse.model_validate(task)
        )
    finally:
        if os.path.exists(image_path):
            try:
                os.unlink(image_path)
            except:
                pass


@router.get("/task/{task_id}", response_model=APIResponse)
def get_size_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    """获取尺码推荐任务状态"""
    task = SizeService.get_task_result(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return APIResponse(
        code=200,
        message="获取成功",
        data=TaskResponse.model_validate(task)
    )