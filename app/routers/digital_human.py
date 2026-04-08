"""
商家数字人定制路由
"""
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.task import APIResponse
from app.schemas.digital_human import (
    DigitalHumanResponse,
    DigitalHumanListResponse,
    DigitalHumanCreateRequest,
    DigitalHumanUpdateRequest
)
from app.services.digital_human_service import DigitalHumanService
from app.utils.file_utils import upload_file_helper

router = APIRouter(prefix="/digital_human", tags=["数字人定制"])


@router.post("/", response_model=APIResponse)
async def create_digital_human(
    name: str = Form(...),
    description: str = Form(None),
    source_video: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    创建数字人

    - **name**: 数字人名称
    - **description**: 描述 (可选)
    - **source_video**: 模特视频 (必填)
    """
    # 上传视频
    file_info = await upload_file_helper(source_video, "digital_human_videos")
    source_video_id = file_info["file_id"]

    # 创建数字人
    digital_human = await DigitalHumanService.create_digital_human(
        db=db,
        merchant_id=current_user.id,
        name=name,
        description=description,
        source_video_id=source_video_id
    )

    return APIResponse(
        code=200,
        message="数字人创建成功",
        data=DigitalHumanResponse.model_validate(digital_human)
    )


@router.get("/", response_model=APIResponse)
def list_digital_humans(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    列出数字人

    - **skip**: 跳过数量
    - **limit**: 限制数量
    """
    items = DigitalHumanService.list_digital_humans(
        db=db,
        merchant_id=current_user.id,
        skip=skip,
        limit=limit
    )
    total = DigitalHumanService.count_digital_humans(
        db=db,
        merchant_id=current_user.id
    )

    return APIResponse(
        code=200,
        message="获取成功",
        data={
            "total": total,
            "items": [DigitalHumanResponse.model_validate(item) for item in items]
        }
    )


@router.get("/{digital_human_id}", response_model=APIResponse)
def get_digital_human(
    digital_human_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取数字人详情
    """
    digital_human = DigitalHumanService.get_digital_human(db, digital_human_id)
    if not digital_human:
        raise HTTPException(status_code=404, detail="数字人不存在")

    # 检查权限 (默认数字人或商家的数字人)
    if not digital_human.is_default and digital_human.merchant_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")

    return APIResponse(
        code=200,
        message="获取成功",
        data=DigitalHumanResponse.model_validate(digital_human)
    )


@router.put("/{digital_human_id}", response_model=APIResponse)
def update_digital_human(
    digital_human_id: int,
    name: str = Form(None),
    description: str = Form(None),
    is_active: bool = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    更新数字人
    """
    digital_human = DigitalHumanService.get_digital_human(db, digital_human_id)
    if not digital_human:
        raise HTTPException(status_code=404, detail="数字人不存在")

    # 检查权限 (只能修改自己的数字人)
    if digital_human.merchant_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权修改")

    updated = DigitalHumanService.update_digital_human(
        db=db,
        digital_human_id=digital_human_id,
        name=name,
        description=description,
        is_active=is_active
    )

    return APIResponse(
        code=200,
        message="更新成功",
        data=DigitalHumanResponse.model_validate(updated)
    )


@router.delete("/{digital_human_id}", response_model=APIResponse)
def delete_digital_human(
    digital_human_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    删除数字人 (软删除)
    """
    digital_human = DigitalHumanService.get_digital_human(db, digital_human_id)
    if not digital_human:
        raise HTTPException(status_code=404, detail="数字人不存在")

    # 检查权限 (只能删除自己的数字人)
    if digital_human.merchant_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除")

    # 不能删除默认数字人
    if digital_human.is_default:
        raise HTTPException(status_code=400, detail="不能删除默认数字人")

    success = DigitalHumanService.delete_digital_human(db, digital_human_id)
    if not success:
        raise HTTPException(status_code=400, detail="删除失败")

    return APIResponse(
        code=200,
        message="删除成功",
        data=None
    )
