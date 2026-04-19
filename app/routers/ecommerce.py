from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user
from app.schemas.ecommerce import VideoTaskRequest
from app.services.ecommerce_service import EcommerceService
import logging

router = APIRouter(prefix="/ecommerce", tags=["电商带货"])
logger = logging.getLogger(__name__)

@router.post("/generate_video")
async def generate_video(
    request: VideoTaskRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    提交AI带货视频生成任务
    """
    service = EcommerceService()
    
    try:
        # 1. 解析商品链接
        product_info = await service.parse_product_url(request.url)
        
        # 2. 生成文案脚本
        script = await service.generate_copywriting(product_info)
        
        # 3. 创建视频任务（在后台执行）
        # 这里应该将任务信息保存到数据库，并返回task_id
        # 为了演示，我们直接调用同步方法
        result = await service.create_product_video(script, request.digital_human_id)
        
        return {
            "code": 200,
            "message": "视频生成任务已提交",
            "data": result
        }
    except Exception as e:
        logger.error(f"生成视频失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 注意：这里还需要添加查询任务状态的接口