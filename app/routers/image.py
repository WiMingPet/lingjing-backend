"""
图片生成路由
"""
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

router = APIRouter(prefix="/image", tags=["图片生成"])


@router.post("/generate", response_model=APIResponse)
async def generate_image(
    prompt: str = Form(...),
    negative_prompt: Optional[str] = Form(None),
    width: int = Form(512),
    height: int = Form(512),
    num_images: int = Form(1),
    reference_image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    """
    生成图片

    - **prompt**: 提示词 (必填)
    - **negative_prompt**: 负面提示词 (可选)
    - **width**: 图片宽度 (默认512)
    - **height**: 图片高度 (默认512)
    - **num_images**: 生成数量 (默认1，最大4)
    - **reference_image**: 参考图片 (可选)
    """
    # 处理参考图上传
    reference_image_id = None
    if reference_image:
        file_url, file_id = await upload_file_helper(reference_image, "reference")
        reference_image_id = file_id

    # 创建任务
    request_data = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "num_images": num_images,
        "reference_image_id": reference_image_id
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

    task = await ImageService.generate_image(db, user_id, request_data)

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