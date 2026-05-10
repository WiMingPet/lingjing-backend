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
from app.utils.credits import check_and_deduct_credits  # ✅ 新增

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
    current_user: User = Depends(get_current_user),  # ✅ 新增
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
    reference_image_url = None
    reference_image_id = None
    
    if reference_image:
        file_url, file_id = await upload_file_helper(reference_image, "reference")
        reference_image_url = file_url
        reference_image_id = file_id
        print(f"[DEBUG] 参考图已上传到 OSS: {reference_image_url}")
    else:
        print(f"[DEBUG] 未提供参考图")

    # 创建任务请求数据
    request_data = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "num_images": num_images,
        "reference_image_id": reference_image_id,
        "reference_image_url": reference_image_url  # 新增：传递参考图 URL
    }
    
    print(f"[DEBUG] 图片生成请求 - prompt: {prompt[:50]}...")
    print(f"[DEBUG] 参考图 URL: {reference_image_url}")

    # ✅ 使用当前登录用户
    user = current_user
    user_id = current_user.id

    # ✅ 检查并扣除 5 点灵境点
    check_and_deduct_credits(user, db, 5, "图片生成")

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