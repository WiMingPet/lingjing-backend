"""
口播带货路由 - 绘蛙版
"""
import os
import datetime
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
from app.rq_app import queue_other
from app.tasks.talking_agent_tasks import generate_talking_agent_task

router = APIRouter(prefix="/talking-agent", tags=["口播带货"])

USE_ASYNC = os.getenv("USE_ASYNC", "false").lower() == "true"
print(f"[TALKING_AGENT] USE_ASYNC = {USE_ASYNC}")

# ========== 绘蛙口播带货定价（点）==========
HUIHUA_PRICES = {
    ("720", 10): 180,
    ("720", 15): 260,
    ("1080", 10): 200,
    ("1080", 15): 300,
}


async def analyze_product_images(image_urls: list) -> str:
    """用通义千问 qwen-vl-max 分析商品图，生成商品描述"""
    import asyncio
    import requests
    from app.config import settings

    def _sync():
        image_url = image_urls[0]

        prompt = """分析这张商品图，输出一段商品描述（300字以内），包含：
- 商品名称
- 材质/成分
- 核心卖点（3~5 个）
- 使用场景
- 目标人群

用中文，直接输出描述文本，不要 JSON，不要 markdown。"""

        resp = requests.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "qwen-vl-max",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": prompt},
                    ],
                }],
                "temperature": 0.7,
            },
            timeout=60,
        )
        if resp.status_code != 200:
            raise Exception(f"qwen-vl 错误: {resp.text[:200]}")
        return resp.json()["choices"][0]["message"]["content"].strip()

    return await asyncio.to_thread(_sync)


@router.post("/generate", response_model=APIResponse)
async def generate_talking_agent(
    product_images: List[UploadFile] = File(...),
    item_description: str = Form(""),
    ratio: str = Form("16:9"),
    resolution: str = Form("1080"),
    output_language: str = Form("zh"),
    enable_voiceover: bool = Form(True),
    enable_subtitle: bool = Form(True),
    duration: int = Form(15),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """口播带货 - 绘蛙版（商品图 + 描述 → 带货视频）"""

    # ========== 参数验证 ==========
    if not product_images or len(product_images) == 0:
        raise HTTPException(400, "请上传商品图（至少 1 张）")
    if len(product_images) > 4:
        raise HTTPException(400, "商品图最多 4 张")
    if len(item_description) > 3000:
        raise HTTPException(400, "商品描述不超过 3000 字")
    if ratio not in ["16:9", "9:16", "1:1"]:
        raise HTTPException(400, "比例仅支持 16:9 / 9:16 / 1:1")
    if resolution not in ["720", "1080"]:
        raise HTTPException(400, "分辨率仅支持 720 / 1080")
    if output_language not in ["zh", "en"]:
        raise HTTPException(400, "语言仅支持 zh / en")
    if duration not in [10, 15]:
        raise HTTPException(400, "时长仅支持 10 / 15 秒")

    # ========== 计算费用 ==========
    cost = HUIHUA_PRICES.get((resolution, duration))
    if not cost:
        raise HTTPException(400, f"无效的分辨率或时长: {resolution}, {duration}")

    # ========== 上传商品图 ==========
    product_image_urls = []
    for img in product_images:
        url, _ = await upload_file_helper(img, "talking_agent/product")
        product_image_urls.append(url)
    print(f"[TALKING_AGENT] 商品图已上传: {product_image_urls}")

    # ========== 如果用户没填描述，用通义千问分析商品图 ==========
    if not item_description or not item_description.strip():
        print(f"[TALKING_AGENT] 用户没填描述，AI 分析中...")
        try:
            item_description = await analyze_product_images(product_image_urls)
            print(f"[TALKING_AGENT] AI 描述: {item_description[:200]}")
        except Exception as e:
            print(f"[TALKING_AGENT] AI 分析失败: {e}")
            raise HTTPException(500, "无法分析商品图，请手动填写商品描述")

    # ========== 构建请求数据 ==========
    request_data = {
        "product_images": product_image_urls,
        "item_description": item_description,
        "ratio": ratio,
        "resolution": resolution,
        "output_language": output_language,
        "enable_voiceover": enable_voiceover,
        "enable_subtitle": enable_subtitle,
        "duration": duration,
    }

    # ========== 检查余额 ==========
    if current_user.credits < cost:
        raise HTTPException(403, f"需要 {cost} 点，当前余额 {current_user.credits} 点，请充值")

    # ========== 判断模式 ==========
    if USE_ASYNC:
        if queue_other is None:
            raise HTTPException(500, "异步队列未初始化")

        check_and_deduct_credits(current_user, db, cost, f"口播带货-{resolution}p-{duration}s")

        from app.models.task import Task
        task = Task(
            user_id=current_user.id,
            task_type="talking_agent",
            status="pending",
            input_data=request_data,
            credits_cost=cost,
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        job = queue_other.enqueue(generate_talking_agent_task, task.id, current_user.id, request_data)
        print(f"[TALKING_AGENT] RQ 任务已提交: task_id={task.id}, job_id={job.id}")

        return APIResponse(
            code=200,
            message=f"口播视频任务已提交，预扣 {cost} 点，预计 10-15 分钟完成",
            data={"task_id": task.id, "status": "pending", "async": True, "cost": cost}
        )
    else:
        # 同步模式（本地测试）
        from app.services.huihua_service import huihua_service
        from app.utils.refund import refund_credits
        from app.models.history import History

        from app.models.task import Task
        task = Task(
            user_id=current_user.id,
            task_type="talking_agent",
            status="processing",
            input_data=request_data,
            credits_cost=cost,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id

        # 扣费
        try:
            check_and_deduct_credits(current_user, db, cost, f"口播带货-{resolution}p-{duration}s")
        except HTTPException:
            task.status = "failed"
            task.error_message = "余额不足"
            db.commit()
            raise

        # 生成
        try:
            hui_task_id = await asyncio.to_thread(
                huihua_service.generate_video,
                product_image_urls,
                item_description,
                ratio,
                resolution,
                output_language,
                enable_voiceover,
                enable_subtitle,
                duration,
            )
            result = await asyncio.to_thread(
                huihua_service.wait_for_result, hui_task_id, 1800, 30
            )
            video_url = result.get("video_url")
            if not video_url:
                raise Exception("绘蛙未返回 video_url")

        except Exception as e:
            error_msg = str(e)
            print(f"[TALKING_AGENT] 失败: {error_msg}")
            task.status = "failed"
            task.error_message = error_msg
            db.commit()
            refund_credits(db, task_id, reason=f"口播带货失败: {error_msg}")
            raise HTTPException(500, f"口播视频生成失败，已退款 {cost} 点")

        # 转存 OSS
        try:
            from app.services.oss_service import oss_service
            oss_video_url = await oss_service.upload_file_from_url(video_url, "mp4", "talking_agent")
            video_url = oss_video_url
        except Exception as e:
            print(f"[TALKING_AGENT] OSS 转存失败: {e}")

        # 封面
        thumbnail_url = None
        try:
            from app.services.video_service import VideoService
            thumbnail_url = await VideoService.extract_thumbnail(video_url)
        except Exception as e:
            print(f"[TALKING_AGENT] 封面失败: {e}")

        # 更新任务
        task.status = "completed"
        task.output_data = {
            "video_url": video_url,
            "thumbnail": thumbnail_url,
            "duration": duration,
            "actual_cost": cost,
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

        return APIResponse(
            code=200,
            message="口播视频生成成功",
            data={"video_url": video_url, "duration": duration, "cost": cost, "history_id": history.id}
        )


@router.get("/task/{task_id}", response_model=APIResponse)
def get_talking_agent_task(task_id: int, db: Session = Depends(get_db)):
    from app.models.task import Task
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(404, "任务不存在")
    return APIResponse(
        code=200, message="获取成功",
        data={
            "task_id": task.id,
            "status": task.status,
            "output_data": task.output_data,
            "error_message": task.error_message,
        }
    )