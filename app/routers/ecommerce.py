from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user
from app.schemas.ecommerce import VideoTaskRequest, ProductInfo
from app.utils.credits import check_and_deduct_credits
from app.data.prices import ECOMMERCE_VIDEO_COST
from app.rq_app import queue_other
from app.tasks.other_tasks import generate_ecommerce_video_task
import os
import logging

# 新增请求模型
from pydantic import BaseModel

class ParseUrlRequest(BaseModel):
    url: str

router = APIRouter(prefix="/ecommerce", tags=["电商带货"])
logger = logging.getLogger(__name__)

# ========== 是否使用异步模式 ==========
USE_ASYNC = os.getenv("USE_ASYNC", "false").lower() == "true"
print(f"[ECOMMERCE] USE_ASYNC = {USE_ASYNC}")
# =====================================


@router.post("/generate_video")
async def generate_video(
    request: VideoTaskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """提交AI带货视频生成任务"""
    cost = ECOMMERCE_VIDEO_COST
    
    # ========== 检查余额 ==========
    if current_user.credits < cost:
        raise HTTPException(status_code=403, detail=f"AI带货视频需要{cost}灵境点，当前余额不足")
    
    # ========== 构建请求数据 ==========
    # VideoTaskRequest 是 Pydantic 对象，需要转成 dict
    request_data = {
        "url": request.url,
        "description": request.description,
        "image_url": request.image_url,
        "digital_image_url": request.digital_image_url,
        "digital_human_id": request.digital_human_id,
    }
    
    # ========== 异步模式 ==========
    if USE_ASYNC:
        print(f"[ECOMMERCE] 使用异步模式")
        
        if queue_other is None:
            raise HTTPException(status_code=500, detail="异步队列未初始化")
        
        # 先扣费
        check_and_deduct_credits(current_user, db, cost, "AI带货视频")
        
        # 创建任务
        from app.models.task import Task
        task = Task(
            user_id=current_user.id,
            task_type="ecommerce",
            status="pending",
            input_data=request_data,
            credits_cost=cost,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        # 提交队列
        job = queue_other.enqueue(
            generate_ecommerce_video_task,
            task.id,
            current_user.id,
            request_data
        )
        print(f"[ECOMMERCE] RQ 任务已提交: task_id={task.id}, job_id={job.id}")
        
        return {
            "code": 200,
            "message": "任务已提交，预计2-5分钟完成",
            "data": {
                "task_id": task.id,
                "status": "pending",
                "async": True
            }
        }
    else:
        # ========== 同步模式（原有逻辑） ==========
        print(f"[ECOMMERCE] 使用同步模式")
        
        from app.services.ecommerce_service import EcommerceService
        from app.models.history import History
        import datetime
        
        service = EcommerceService()
        
        try:
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
            
            is_manual = not request.url and (request.image_url or request.description)
            
            # 2. 生成文案
            script = await service.generate_copywriting(product, is_manual_mode=is_manual)
            
            # 3. 生成视频
            result = await service.create_product_video(
                script,
                product,
                digital_image_url=request.digital_image_url,
                digital_human_id=request.digital_human_id,
                user_token=None,
                is_manual_mode=is_manual
            )
            
            video_url = result.get("video_url")
            if not video_url:
                raise Exception("视频生成失败")
            
            # 4. 生成封面
            thumbnail_url = None
            try:
                from app.services.video_service import VideoService
                thumbnail_url = await VideoService.extract_thumbnail(video_url)
            except Exception as e:
                print(f"[DEBUG] 封面图生成失败: {e}")
            
            # 5. 生成成功后扣费
            check_and_deduct_credits(current_user, db, cost, "AI带货视频")
            
            # 6. 保存历史记录
            existing = db.query(History).filter(
                History.user_id == current_user.id,
                History.url == video_url,
                History.type == "AI带货视频"
            ).first()
            
            if not existing:
                history = History(
                    user_id=current_user.id,
                    url=video_url,
                    type="AI带货视频",
                    thumbnail=thumbnail_url,
                    created_at=datetime.datetime.utcnow()
                )
                db.add(history)
                db.commit()
            
            return {
                "code": 200,
                "message": "视频生成成功",
                "data": {
                    "video_url": video_url,
                    "thumbnail": thumbnail_url
                }
            }
        
        except Exception as e:
            logger.error(f"生成视频失败: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/task/{task_id}")
async def get_task_status(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """查询异步任务状态"""
    from app.models.task import Task
    
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 验证任务所属
    if task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")
    
    return {
        "code": 200,
        "message": "获取成功",
        "data": {
            "task_id": task.id,
            "status": task.status,
            "message": task.error_message if task.status == "failed" else "处理中",
            "video_url": task.output_data.get("video_url") if task.output_data else None,
            "thumbnail": task.output_data.get("thumbnail") if task.output_data else None,
        }
    }


@router.post("/parse_url")
async def parse_url(
    request: ParseUrlRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """解析商品链接"""
    import re
    from app.services.ecommerce_service import EcommerceService
    
    raw = request.url.strip()
    logger.info(f"原始输入: {raw}")
    
    douyin_patterns = [
        r'https?://v\.douyin\.com/\w+',
        r'https?://www\.douyin\.com/video/\d+',
        r'https?://www\.iesdouyin\.com/share/video/\d+',
    ]
    
    url = None
    for pattern in douyin_patterns:
        match = re.search(pattern, raw)
        if match:
            url = match.group(0)
            break
    
    if not url:
        raise HTTPException(status_code=400, detail="未识别到有效的抖音链接，请复制完整链接")
    
    logger.info(f"提取后的链接: {url}")
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
        raise HTTPException(status_code=500, detail="解析失败，请确认链接有效后重试")