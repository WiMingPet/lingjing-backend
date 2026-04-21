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
            digital_human_id=request.digital_human_id
        )
        
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
    request: ParseUrlRequest,  # ← 改为接收 JSON body
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    解析商品链接，获取商品信息
    优先使用订单侠解析抖音链接
    """
    from app.services.dingdanxia import parse_douyin_command
    
    url = request.url  # ← 从 body 中获取 url
    service = EcommerceService()
    
    # 判断是否是抖音链接
    is_douyin_link = "douyin.com" in url or "iesdouyin.com" in url or "haohuo.jinritemai.com" in url
    
    # 如果是抖音链接，优先用订单侠
    if is_douyin_link:
        logger.info(f"检测到抖音链接，使用订单侠解析: {url}")
        parse_result = parse_douyin_command(url)
        
        if parse_result["success"]:
            logger.info(f"订单侠解析成功: {parse_result['title']}")
            return {
                "code": 200,
                "message": "解析成功",
                "data": {
                    "title": parse_result["title"],
                    "price": str(parse_result["price"]),
                    "description": parse_result["title"],
                    "images": [],
                    "need_image": True
                }
            }
        else:
            logger.warning(f"订单侠解析失败: {parse_result['error']}，尝试原有解析")
    
    # 原有解析逻辑
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
                "need_image": False
            }
        }
    except Exception as e:
        logger.error(f"解析失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))