"""
多角度试穿路由
"""
from fastapi import APIRouter, Depends, HTTPException, File, Form
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database import get_db
from app.schemas.task import APIResponse, TaskResponse
from app.services.multi_angle_service import MultiAngleService

router = APIRouter(prefix="/multi-angle", tags=["多角度试穿"])


@router.post("/generate", response_model=APIResponse)
async def generate_unified_character(
    prompt: Optional[str] = Form("A full body photo of a person, consistent appearance"),
    db: Session = Depends(get_db),
):
    """
    多角度合成统一角色 - 使用测试图片
    """
    # 使用公网测试图片
    subject_images = [
        "https://picsum.photos/id/100/512/512",
        "https://picsum.photos/id/101/512/512"
    ]
    
    print(f"[DEBUG] 使用测试图片URL: {subject_images}")
    
    request_data = {
        "subject_images": subject_images,
        "prompt": prompt
    }
    
    user_id = 1
    task = await MultiAngleService.generate_unified_character(db, user_id, request_data)
    
    return APIResponse(
        code=200,
        message="多角度合成任务已提交",
        data=TaskResponse.model_validate(task)
    )


@router.get("/task/{task_id}", response_model=APIResponse)
def get_multi_angle_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    """获取多角度合成任务状态"""
    task = MultiAngleService.get_task_result(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return APIResponse(
        code=200,
        message="获取成功",
        data=TaskResponse.model_validate(task)
    )