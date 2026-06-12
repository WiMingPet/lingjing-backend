from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user
from app.services.dingdanxia import get_douyin_product_info
from app.services.kling import KlingService
from app.services.ecommerce_service import EcommerceService
import logging

router = APIRouter(prefix="/link-to-video", tags=["链接转视频"])
logger = logging.getLogger(__name__)


class LinkRequest(BaseModel):
    url: str


@router.post("/generate")
async def generate_video_from_link(
    request: LinkRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """用户输入抖音链接，自动生成带货视频"""
    try:
        # 1. 获取商品信息
        product = await get_douyin_product_info(request.url)
        if not product["image_url"]:
            raise HTTPException(status_code=400, detail="无法获取商品图片")
        
        # 2. 生成口播文案（复用你已有的 AI 生成能力）
        ecommerce_service = EcommerceService()
        script = await ecommerce_service.generate_copywriting(
            product_info=product
        )
        
        # 3. 调用可灵生成视频
        kling = KlingService()
        
        # 3a. 虚拟试穿（用商品主图作为服装图）
        # 注意：这里需要一张模特图，可以用默认的或从其他地方获取
        default_model_image = "https://media.lingjing-media.com/default/model.jpg"
        tryon_task = await kling.generate_tryon(
            human_image_url=default_model_image,
            cloth_image_url=product["image_url"]
        )
        tryon_video_url = await kling.wait_for_tryon_result(tryon_task)
        
        # 3b. 数字人分身（用商品主图作为数字人照片）
        digital_task = await kling.generate_digital_human(
            image_url=product["image_url"],
            text=script.script
        )
        digital_video_url = await kling.wait_for_digital_human_result(digital_task)
        
        # 4. 合并视频（如果有需要）
        final_video_url = await ecommerce_service._merge_videos(
            digital_video_url, 
            [tryon_video_url]
        )
        
        return {
            "code": 200,
            "message": "视频生成成功",
            "data": {
                "video_url": final_video_url,
                "product": product
            }
        }
        
    except Exception as e:
        logger.error(f"生成失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))