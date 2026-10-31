"""
商品成片 RQ 任务 - 可灵商品成片
"""
import datetime
from app.database import SessionLocal
from app.models.task import Task
from app.models.history import History
from app.utils.refund import refund_credits


def generate_goods_studio_task(task_id: int, user_id: int, request_data: dict):
    print(f"[GOODS_STUDIO] 开始: task_id={task_id}, user_id={user_id}")

    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return {"error": "任务不存在"}

        task.status = "processing"
        db.commit()

        from app.services.kling import kling_service

        # 提交任务
        api_task_id = kling_service.generate_goods_studio(
            image_urls=request_data["image_urls"],
            title=request_data["title"],
            description=request_data.get("description", ""),
            resolution=request_data.get("resolution", "1080p"),
            aspect_ratio=request_data.get("aspect_ratio", "16:9"),
            duration=request_data.get("duration", 15),
        )
        print(f"[GOODS_STUDIO] 任务已提交: {api_task_id}")

        # 轮询
        result = kling_service.wait_for_goods_studio_result(api_task_id, max_wait=1800)
        video_url = result.get("video_url")
        if not video_url:
            raise Exception("商品成片未返回 video_url")

        # 转存 OSS
        try:
            from app.services.oss_service import oss_service
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                oss_url = loop.run_until_complete(
                    oss_service.upload_file_from_url(video_url, "mp4", "goods_studio")
                )
            finally:
                loop.close()
            video_url = oss_url
            print(f"[GOODS_STUDIO] 转存 OSS: {video_url}")
        except Exception as e:
            print(f"[GOODS_STUDIO] OSS 转存失败: {e}")

        # 封面
        thumbnail_url = None
        try:
            from app.services.video_service import VideoService
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                thumbnail_url = loop.run_until_complete(VideoService.extract_thumbnail(video_url))
            finally:
                loop.close()
        except Exception as e:
            print(f"[GOODS_STUDIO] 封面失败: {e}")

        # 更新任务
        task.status = "completed"
        task.output_data = {
            "video_url": video_url,
            "thumbnail": thumbnail_url,
            "duration": request_data.get("duration", 15),
        }
        task.progress = 100
        task.completed_at = datetime.datetime.utcnow()
        db.commit()

        # 历史
        existing = db.query(History).filter(
            History.user_id == user_id,
            History.url == video_url
        ).first()
        if not existing:
            history = History(
                user_id=user_id,
                url=video_url,
                type="商品成片",
                thumbnail=thumbnail_url,
                created_at=datetime.datetime.utcnow()
            )
            db.add(history)
            db.commit()

        print(f"[GOODS_STUDIO] 完成: task_id={task_id}")
        return {"task_id": task_id, "status": "completed"}

    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"[GOODS_STUDIO] 失败: {error_msg}")
        print(traceback.format_exc())

        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = "failed"
                task.error_message = error_msg
                db.commit()
        except Exception as e2:
            print(f"[GOODS_STUDIO] 更新失败状态出错: {e2}")

        refund_credits(db, task_id, reason=f"商品成片失败: {error_msg}")
        return {"task_id": task_id, "status": "failed", "error": error_msg}

    finally:
        db.close()