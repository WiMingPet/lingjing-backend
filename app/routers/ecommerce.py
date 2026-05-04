from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user
from app.schemas.ecommerce import VideoTaskRequest, ProductInfo
from app.services.ecommerce_service import EcommerceService
import logging

# ========== 添加请求模型 ==========
from pydantic import BaseModel

class ParseUrlRequest(BaseModel):
    url: str
# ========== 添加结束 ==========

router = APIRouter(prefix="/ecommerce", tags=["电商带货"])
logger = logging.getLogger(__name__)


@router.post("/generate_video")
async def generate_video(
    request: VideoTaskRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """提交AI带货视频生成任务"""
    service = EcommerceService()
    
    # 提取用户token用于内部API调用
    from fastapi import Request
    # 注：这里需要通过依赖注入获取token，先用简单方式
    user_token = None  # FastAPI中较难直接获取原始token，可传空（试穿接口可能需要调整）
    
    try:
        product = None
        if request.url:
            try:
                product = await service.parse_product_url(request.url)
            except Exception as e:
                logger.warning(f"解析URL失败: {e}")
                product = None
        
        if not product:
            product = ProductInfo(
                title="商品",
                price="0",
                description=request.description or "",
                images=[request.image_url] if request.image_url else [],
                platform="manual"
            )
        
        script = await service.generate_copywriting(product)
        
        result = await service.create_product_video(
            script, 
            product, 
            digital_image_url=request.digital_image_url,
            digital_human_id=request.digital_human_id,
            user_token=user_token
        )
        
        # 【修复3】保存历史记录
        from app.models.history import History
        import datetime
        history = History(
            user_id=current_user.id,
            url=result["video_url"],
            type="AI带货视频",
            thumbnail=None,
            created_at=datetime.datetime.utcnow()
        )
        db.add(history)
        db.commit()
        
        return {
            "code": 200,
            "message": "视频生成成功",
            "data": result
        }
    except Exception as e:
        logger.error(f"生成视频失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== 修改 parse_url 接口 ==========
@router.post("/parse_url")
async def parse_url(
    request: ParseUrlRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    解析商品链接，获取商品信息
    优先使用本地解析，失败时再尝试订单侠
    """
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