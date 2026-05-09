from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user
from app.schemas.ecommerce import VideoTaskRequest, ProductInfo
from app.services.ecommerce_service import EcommerceService
from app.utils.credits import check_and_deduct_credits
from app.models.history import History
import datetime
import logging

# 新增请求模型
from pydantic import BaseModel

class ParseUrlRequest(BaseModel):
    url: str

router = APIRouter(prefix="/ecommerce", tags=["电商带货"])
logger = logging.getLogger(__name__)


# ========== 新增：存储任务状态的简易字典（生产环境应改用数据库表） ==========
task_store = {}

async def _generate_video_background(
    task_id: str,
    user_id: int,
    request: VideoTaskRequest,
    db: Session
):
    """后台生成带货视频"""
    service = EcommerceService()
    
    try:
        task_store[task_id] = {"status": "processing", "message": "正在解析商品信息..."}
        
        # 1. 解析商品
        product = None
        if request.url:
            try:
                product = await service.parse_product_url(request.url)
            except Exception as e:
                logger.warning(f"解析URL失败: {e}")
        
        if not product:
            product = ProductInfo(
                title="商品",
                price="0",
                description=request.description or "",
                images=[request.image_url] if request.image_url else [],
                platform="manual"
            )
        
        # 判断是否为手动模式（没有链接，只有图片或描述）
        is_manual = not request.url and (request.image_url or request.description)
        
        task_store[task_id] = {"status": "processing", "message": "正在生成口播文案..."}
        
        # 2. 生成文案
        script = await service.generate_copywriting(product, is_manual_mode=is_manual)
        
        task_store[task_id] = {"status": "processing", "message": "正在生成带货视频，预计2-5分钟..."}
        
        # 3. 生成视频
        result = await service.create_product_video(
            script, 
            product, 
            digital_image_url=request.digital_image_url,
            digital_human_id=request.digital_human_id,
            user_token=None,
            is_manual_mode=is_manual
        )
        
        
        task_store[task_id] = {
            "status": "completed",
            "message": "视频生成成功",
            "video_url": result["video_url"]
        }
        # 保存历史记录
        history = History(
            user_id=user_id,
            url=result["video_url"],
            type="AI带货视频",
            thumbnail=None,
            created_at=datetime.datetime.utcnow()
        )
        db.add(history)
        db.commit()
        
    except Exception as e:
        logger.error(f"后台生成视频失败: {str(e)}")
        task_store[task_id] = {"status": "failed", "message": str(e)}


@router.post("/generate_video")
async def generate_video(
    request: VideoTaskRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """提交AI带货视频生成任务（异步后台执行）"""
    # ✅ 先检查余额，余额不足直接拒绝
    check_and_deduct_credits(current_user, db, 20, "AI带货视频")

    import uuid
    task_id = str(uuid.uuid4())
    
    # 初始化任务状态
    task_store[task_id] = {"status": "pending", "message": "任务已提交"}
    
    # 放入后台执行
    background_tasks.add_task(
        _generate_video_background,
        task_id=task_id,
        user_id=current_user.id,
        request=request,
        db=db
    )
    
    return {
        "code": 200,
        "message": "任务已提交，正在后台生成",
        "data": {
            "task_id": task_id,
            "status": "pending"
        }
    }


@router.get("/task/{task_id}")
async def get_task_status(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """查询异步任务状态"""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return {
        "code": 200,
        "message": "获取成功",
        "data": task
    }


@router.post("/parse_url")
async def parse_url(
    request: ParseUrlRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """解析商品链接"""
    url = request.url
    service = EcommerceService()
    
    try:
        product = await service.parse_product_url(url)
        return {
            "code": 200,
            "message": "解析成功",
            "data": {
                "title": product.title,
                "price": product.price,
                "description": product.description,
                "images": product.images,
                "need_image": len(product.images) == 0
            }
        }
    except Exception as e:
        logger.error(f"解析失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))