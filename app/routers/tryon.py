"""
虚拟试穿路由
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from app.database import get_db
from app.schemas.task import APIResponse, TaskResponse
from app.services.tryon_service import TryonService
from app.models.user import User
from app.utils.file_utils import upload_file_helper  # 新增：导入 OSS 上传工具
from app.utils.credits import check_and_deduct_credits  # ✅ 新增：导入扣除工具
from app.utils.auth import get_current_user  # ✅ 新增：导入获取用户工具

router = APIRouter(prefix="/tryon", tags=["虚拟试穿"])

# ========== 新增：可选认证依赖 ==========
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
    """
    虚拟试穿

    - **model_image**: 模特图片（必填）
    - **garment_image**: 服装图片（必填）
    - **digital_human_id**: 数字人ID（可选）
    """
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
    
    # ✅ 直接使用当前登录用户
    user = current_user
    user_id = current_user.id

    # ✅ 生成前检查余额（不扣除）
    if user.credits < 10:
        raise HTTPException(status_code=403, detail="虚拟试穿需要10灵境点，当前余额不足，请充值")
        
    task = await TryonService.generate_tryon(db, user_id, request_data)
    
    if task.status != "completed":
        raise HTTPException(500, detail=task.error_message or "虚拟试穿失败")
    
    # ✅ 生成成功后扣点
    check_and_deduct_credits(user, db, 10, "虚拟试穿")
    
    # ========== ✅ 后端自动保存历史记录 ==========
    try:
        from app.routers.history import save_history
        from app.schemas.history import SaveHistoryRequest
        
        output_data = task.output_data or {}
        video_url = output_data.get("video_url")
        tryon_image_url = output_data.get("tryon_image_url")
        
        if video_url:
            history_request = SaveHistoryRequest(
                url=video_url,
                type="虚拟试穿",
                thumbnail=tryon_image_url
            )
            await save_history(history_request, db, current_user)
            print(f"[DEBUG] ✅ 试穿历史记录已自动保存")
    except Exception as e:
        print(f"[DEBUG] ⚠️ 历史记录保存失败（不影响主流程）: {e}")
    
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
# ========== 新增：通过URL生成试穿（服务器内部专用） ==========
import os

class TryonByUrlRequest(BaseModel):
    model_image_url: str
    garment_image_url: str

@router.post("/generate_by_url", response_model=APIResponse)
async def generate_tryon_by_url(
    request: TryonByUrlRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_optional),  # ← 改为可选认证
    x_internal_key: str = Header(None, alias="X-Internal-Key")
):
    """
    通过图片URL生成虚拟试穿（服务器内部专用）
    
    - **model_image_url**: 模特图片URL
    - **garment_image_url**: 服装图片URL
    """
    # 安全校验：仅允许服务器内部调用
    INTERNAL_KEY = os.getenv("INTERNAL_API_KEY", "lingjing-internal-2026")
    if x_internal_key != INTERNAL_KEY:
        raise HTTPException(status_code=403, detail="仅限内部调用")
    
    # ✅ 只有用户登录时才扣点（内部调用免扣点）
    if current_user:
        check_and_deduct_credits(current_user, db, 10, "虚拟试穿")
    
    request_data = {
        "model_image_url": request.model_image_url,
        "garment_image_url": request.garment_image_url,
        "title": "",
        "cloth_category": ""
    }
    
    task = await TryonService.generate_tryon(db, current_user.id if current_user else 1, request_data)
    
    return APIResponse(
        code=200,
        message="虚拟试穿任务已提交",
        data=TaskResponse.model_validate(task)
    )