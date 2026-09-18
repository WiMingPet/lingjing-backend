"""
口播带货路由
"""
import os
import math
import asyncio
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user
from app.schemas.task import APIResponse
from app.utils.file_utils import upload_file_helper
from app.utils.credits import check_and_deduct_credits
from app.data.prices import (
    TALKING_AGENT_COST_PER_SECOND,
    TALKING_AGENT_MIN_SECONDS,
    TALKING_AGENT_WORDS_PER_SECOND
)
from app.rq_app import queue_other
from app.tasks.talking_agent_tasks import generate_talking_agent_task

router = APIRouter(prefix="/talking-agent", tags=["口播带货"])

# ========== 是否使用异步模式 ==========
USE_ASYNC = os.getenv("USE_ASYNC", "false").lower() == "true"
print(f"[TALKING_AGENT] USE_ASYNC = {USE_ASYNC}")
# =====================================


@router.post("/generate", response_model=APIResponse)
async def generate_talking_agent(
    avatar_image: Optional[UploadFile] = File(None),
    avatar_id: Optional[str] = Form(None),
    voice_id: Optional[str] = Form(None),
    product_images: Optional[List[UploadFile]] = File(None),
    goods_title: Optional[str] = Form(None),
    goods_price: Optional[str] = Form(None),
    target_audience: Optional[str] = Form(None),
    selling_point: Optional[str] = Form(None),
    script: str = Form(...),
    resolution: str = Form("720p"),
    aspect_ratio: str = Form("9:16"),
    allow_polish: bool = Form(False),
    bgm_enabled: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """口播带货 - 达人口播 / 口播带货"""
    
    # ========== 参数验证 ==========
    if not avatar_image and not avatar_id:
        raise HTTPException(400, "请上传人物图或选择预设形象")
    
    if avatar_image and avatar_id:
        raise HTTPException(400, "人物图与预设形象只能二选一")
    
    if avatar_image and not voice_id:
        raise HTTPException(400, "上传人物图时，必须指定音色")
    
    if avatar_id and voice_id:
        raise HTTPException(400, "使用预设形象时，禁止传入音色")
    
    if not script or not script.strip():
        raise HTTPException(400, "请填写口播稿")
    
    if resolution not in ["720p", "1080p"]:
        raise HTTPException(400, "分辨率仅支持 720p 和 1080p")
    
    if aspect_ratio not in ["9:16", "16:9"]:
        raise HTTPException(400, "画幅仅支持 9:16 和 16:9")
    
    # ========== 上传人物图 ==========
    avatar_image_url = None
    if avatar_image:
        avatar_image_url, _ = await upload_file_helper(avatar_image, "talking_agent/avatar")
        print(f"[DEBUG] 人物图已上传: {avatar_image_url}")
    
    # ========== 上传商品图 ==========
    product_image_urls = []
    if product_images:
        if len(product_images) > 5:
            raise HTTPException(400, "商品图最多 5 张")
        for img in product_images:
            url, _ = await upload_file_helper(img, "talking_agent/product")
            product_image_urls.append(url)
        print(f"[DEBUG] 商品图已上传: {product_image_urls}")
    
    # ========== 有商品信息必须有商品图和标题 ==========
    has_product = bool(product_image_urls or goods_title or goods_price or target_audience or selling_point)
    if has_product:
        if not product_image_urls:
            raise HTTPException(400, "请上传商品图（至少 1 张）")
        if not goods_title:
            raise HTTPException(400, "请填写商品标题")
    
    # ========== 计算预估时长和费用 ==========
    script_length = len(script)
    estimated_seconds = max(
        TALKING_AGENT_MIN_SECONDS,
        math.ceil(script_length / TALKING_AGENT_WORDS_PER_SECOND)
    )
    estimated_cost = estimated_seconds * TALKING_AGENT_COST_PER_SECOND
    print(f"[DEBUG] 口播稿 {script_length} 字，预估 {estimated_seconds} 秒，预扣 {estimated_cost} 点")
    
    # ========== 检查余额 ==========
    if current_user.credits < estimated_cost:
        raise HTTPException(
            403,
            f"口播稿 {script_length} 字，预估 {estimated_seconds} 秒，需要 {estimated_cost} 点，当前余额 {current_user.credits} 点，请充值"
        )
    
    # ========== 构建请求数据 ==========
    request_data = {
        "avatar_image_url": avatar_image_url,
        "avatar_id": avatar_id,
        "voice_id": voice_id if avatar_image_url else None,
        "product_images": product_image_urls,
        "goods_title": goods_title,
        "goods_price": goods_price,
        "target_audience": target_audience,
        "selling_point": selling_point,
        "script": script,
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
        "allow_polish": allow_polish,
        "bgm_enabled": bgm_enabled,
        "estimated_seconds": estimated_seconds,
        "estimated_cost": estimated_cost,
    }
    
    # ========== 判断模式 ==========
    if USE_ASYNC:
        if queue_other is None:
            raise HTTPException(500, "异步队列未初始化")
        
        # 原子扣费（预扣）
        check_and_deduct_credits(current_user, db, estimated_cost, "口播带货")
        
        # 创建任务
        from app.models.task import Task
        task = Task(
            user_id=current_user.id,
            task_type="talking_agent",
            status="pending",
            input_data=request_data,
            credits_cost=estimated_cost,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        # 提交队列
        job = queue_other.enqueue(generate_talking_agent_task, task.id, current_user.id, request_data)
        print(f"[TALKING_AGENT] RQ 任务已提交: task_id={task.id}, job_id={job.id}")
        
        return APIResponse(
            code=200,
            message=f"口播稿 {script_length} 字，预估 {estimated_seconds} 秒，预扣 {estimated_cost} 点",
            data={
                "task_id": task.id,
                "status": "pending",
                "async": True,
                "estimated_seconds": estimated_seconds,
                "estimated_cost": estimated_cost,
            }
        )
    else:
        # 同步模式
        from app.services.kling import kling_service
        from app.utils.refund import refund_credits
        from app.models.history import History
        import datetime

        # ========== 先创建 Task 记录（用于幂等退款）==========
        from app.models.task import Task
        task = Task(
            user_id=current_user.id,
            task_type="talking_agent",
            status="processing",
            input_data=request_data,
            credits_cost=estimated_cost,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id
        # ====================================================

        # ========== 扣费 ==========
        try:
            check_and_deduct_credits(current_user, db, estimated_cost, "口播带货")
            print(f"[TALKING_AGENT] 预扣 {estimated_cost} 点成功, task_id={task_id}")
        except HTTPException:
            # 扣费失败，标记任务失败
            task.status = "failed"
            task.error_message = "余额不足"
            db.commit()
            raise
        # ========================

        # ========== 生成 ==========
        try:
            result = await asyncio.to_thread(kling_service.generate_talking_agent, request_data)
            video_url = result.get("video_url")
            actual_duration = float(result.get("duration", 0))

            if not video_url:
                raise Exception("可灵返回没有 video_url")

        except Exception as e:
            # 生成失败：标记任务失败 + 幂等退款
            error_msg = str(e)
            print(f"[TALKING_AGENT] 生成失败，准备退款: {error_msg}")

            task.status = "failed"
            task.error_message = error_msg
            db.commit()

            # 幂等退款：refund_credits 内部有 refunded 标记防重复
            refunded = refund_credits(db, task_id, reason=f"口播带货生成失败: {error_msg}")
            if refunded:
                print(f"[TALKING_AGENT] 已退款 {estimated_cost} 点, task_id={task_id}")
            else:
                print(f"[TALKING_AGENT] 退款失败或已退款, task_id={task_id}")

            raise HTTPException(500, f"口播视频生成失败，已退款 {estimated_cost} 点")
        # ========================

        # ========== 生成成功，后续处理失败不退款 ==========

        # 转存 OSS
        try:
            from app.services.oss_service import oss_service
            oss_video_url = await oss_service.upload_file_from_url(
                video_url, "mp4", "talking_agent"
            )
            video_url = oss_video_url
            print(f"[TALKING_AGENT] 视频已转存 OSS: {video_url}")
        except Exception as e:
            print(f"[TALKING_AGENT] OSS 转存失败，使用原始 URL: {e}")

        # 提取封面
        thumbnail_url = None
        try:
            from app.services.video_service import VideoService
            thumbnail_url = await VideoService.extract_thumbnail(video_url)
            print(f"[TALKING_AGENT] 封面生成成功: {thumbnail_url}")
        except Exception as e:
            print(f"[TALKING_AGENT] 封面提取失败: {e}")

        # ========== 结算：按实际时长，多退少不补 ==========
        actual_cost = int(actual_duration * TALKING_AGENT_COST_PER_SECOND)
        refund_amount = 0
        if actual_cost < estimated_cost:
            refund_amount = estimated_cost - actual_cost
            current_user.credits += refund_amount
            task.credits_cost = actual_cost
            db.commit()
            print(f"[TALKING_AGENT] 结算: 预扣{estimated_cost}, 实际{actual_cost}, 退款{refund_amount}")
        else:
            print(f"[TALKING_AGENT] 结算: 实际{actual_cost} ≥ 预扣{estimated_cost}, 不补扣")
        # ================================================

        # ========== 更新 Task + 保存历史 ==========
        task.status = "completed"
        task.output_data = {
            "video_url": video_url,
            "thumbnail": thumbnail_url,
            "duration": actual_duration,
            "actual_cost": actual_cost,
            "estimated_cost": estimated_cost,
            "refund": refund_amount,
        }
        task.progress = 100
        task.completed_at = datetime.datetime.utcnow()
        db.commit()

        history = History(
            user_id=current_user.id,
            url=video_url,
            type="口播带货",
            thumbnail=thumbnail_url,
            created_at=datetime.datetime.utcnow()
        )
        db.add(history)
        db.commit()
        print(f"[TALKING_AGENT] 历史记录已保存: history_id={history.id}")
        # ==========================================

        return APIResponse(
            code=200,
            message="口播视频生成成功",
            data={
                "video_url": video_url,
                "duration": actual_duration,
                "actual_cost": actual_cost,
                "estimated_cost": estimated_cost,
                "refund": refund_amount,
                "history_id": history.id,
            }
        )


@router.get("/task/{task_id}", response_model=APIResponse)
def get_talking_agent_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    """获取口播带货任务状态"""
    from app.models.task import Task
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(404, "任务不存在")
    
    return APIResponse(
        code=200,
        message="获取成功",
        data={
            "task_id": task.id,
            "status": task.status,
            "output_data": task.output_data,
            "error_message": task.error_message,
        }
    )