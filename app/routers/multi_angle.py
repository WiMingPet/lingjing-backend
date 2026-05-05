"""
多角度试穿路由
"""
from fastapi import APIRouter, Depends, HTTPException, File, Form
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database import get_db
from app.schemas.task import APIResponse, TaskResponse
from app.services.multi_angle_service import MultiAngleService
from app.models.user import User  # ✅ 新增：导入用户模型
from app.utils.credits import check_and_deduct_credits  # ✅ 新增：导入扣除工具
from app.utils.auth import get_current_user  # ✅ 新增：导入获取用户工具

router = APIRouter(prefix="/multi-angle", tags=["多角度试穿"])


@router.post("/generate", response_model=APIResponse)
async def generate_unified_character(
    prompt: Optional[str] = Form("A full body photo of a person, consistent appearance"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # ✅ 新增：从token获取用户
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
    
    # ✅ 新增：检查并扣除 10 点灵境点
    check_and_deduct_credits(user, db, 10, "多角度试穿")
    
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