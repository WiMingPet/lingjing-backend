from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user
from app.schemas.ecommerce import VideoTaskRequest, ProductInfo
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
    支持两种模式：
    1. 手动输入：提供 title, price, description, image_url
    2. 链接解析：提供 url，自动填充信息
    """
    service = EcommerceService()
    
    try:
        # 构建商品信息
        # 如果有 url 且没有手动输入，尝试解析
        if request.url and not request.title:
            product = await service.parse_product_url(request.url)
        else:
            # 使用手动输入的信息
            product = ProductInfo(
                title=request.title,
                price=request.price,
                description=request.description,
                images=[request.image_url] if request.image_url else [],
                platform="manual"
            )
        
        # 生成文案脚本
        script = await service.generate_copywriting(product)
        
        # 生成视频
        result = await service.create_product_video(script, product, request.digital_human_id)
        
        return {
            "code": 200,
            "message": "视频生成成功",
            "data": result
        }
    except Exception as e:
        logger.error(f"生成视频失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/parse_url")
async def parse_url(
    url: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    解析商品链接，获取商品信息
    """
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
                "images": product.images
            }
        }
    except Exception as e:
        logger.error(f"解析失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))