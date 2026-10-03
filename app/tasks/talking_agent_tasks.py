"""
口播带货 RQ 任务 - 绘蛙版
"""
import asyncio
import datetime
from app.database import SessionLocal
from app.models.task import Task
from app.models.history import History
from app.models.user import User
from app.utils.refund import refund_credits

HUIHUA_PRICES = {
    ("720", 10): 180,
    ("720", 15): 260,
    ("1080", 10): 200,
    ("1080", 15): 300,
}

def _run_async(coro):
    """在当前线程跑 async 函数"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def generate_talking_agent_task(task_id: int, user_id: int, request_data: dict):
    """后台执行口播带货生成（绘蛙）"""
    print(f"[RQ-TALKING] 开始: task_id={task_id}, user_id={user_id}")

    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return {"error": "任务不存在"}

        task.status = "processing"
        db.commit()

        from app.services.huihua_service import huihua_service

        # ========== 提交绘蛙 ==========
        hui_task_id = huihua_service.generate_video(
            item_image_urls=request_data["product_images"],
            item_description=request_data["item_description"],
            ratio=request_data.get("ratio", "16:9"),
            resolution=request_data.get("resolution", "1080"),
            output_language=request_data.get("output_language", "zh"),
            enable_voiceover=request_data.get("enable_voiceover", True),
            enable_subtitle=request_data.get("enable_subtitle", True),
            duration=request_data.get("duration", 15),
        )
        print(f"[RQ-TALKING] 绘蛙任务已提交: hui_task_id={hui_task_id}")

        # ========== 轮询 ==========
        result = huihua_service.wait_for_result(hui_task_id, max_wait=1800, poll_interval=30)
        video_url = result.get("video_url")
        if not video_url:
            raise Exception("绘蛙未返回 video_url")

        # ========== 转存 OSS ==========
        try:
            from app.services.oss_service import oss_service
            oss_video_url = _run_async(
                oss_service.upload_file_from_url(video_url, "mp4", "talking_agent")
            )
            video_url = oss_video_url
            print(f"[RQ-TALKING] 转存 OSS: {video_url}")
        except Exception as e:
            print(f"[RQ-TALKING] OSS 转存失败: {e}")

        # ========== 封面 ==========
        thumbnail_url = None
        try:
            from app.services.video_service import VideoService
            thumbnail_url = _run_async(VideoService.extract_thumbnail(video_url))
        except Exception as e:
            print(f"[RQ-TALKING] 封面失败: {e}")

        # ========== 更新任务 ==========
        task.status = "completed"
        task.output_data = {
            "video_url": video_url,
            "thumbnail": thumbnail_url,
            "duration": request_data.get("duration", 15),
            "actual_cost": task.credits_cost,
        }
        task.progress = 100
        task.completed_at = datetime.datetime.utcnow()
        db.commit()

        # 历史记录
        existing = db.query(History).filter(
            History.user_id == user_id,
            History.url == video_url
        ).first()
        if not existing:
            history = History(
                user_id=user_id,
                url=video_url,
                type="口播带货",
                thumbnail=thumbnail_url,
                created_at=datetime.datetime.utcnow()
            )
            db.add(history)
            db.commit()

        print(f"[RQ-TALKING] 完成: task_id={task_id}")
        return {"task_id": task_id, "status": "completed"}

    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"[RQ-TALKING] 失败: task_id={task_id}, error={error_msg}")
        print(traceback.format_exc())

        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = "failed"
                task.error_message = error_msg
                db.commit()
        except Exception as e2:
            print(f"[RQ-TALKING] 更新失败状态出错: {e2}")

        # ★ 失败退款（幂等）
        refund_credits(db, task_id, reason=f"口播带货失败: {error_msg}")
        return {"task_id": task_id, "status": "failed", "error": error_msg}

    finally:
        db.close()