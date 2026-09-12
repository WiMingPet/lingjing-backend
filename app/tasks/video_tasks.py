"""
视频生成 RQ 任务
"""
import asyncio
import datetime
from app.database import SessionLocal
from app.models.task import Task
from app.models.history import History


def generate_video_task(task_id: int, user_id: int, request_data: dict):
    """后台执行视频生成"""
    print(f"[RQ] 开始执行视频生成任务: task_id={task_id}, user_id={user_id}")
    
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            print(f"[RQ] 任务不存在: {task_id}")
            return {"error": "任务不存在"}
        
        task.status = "processing"
        db.commit()
        print(f"[RQ] 任务状态更新为 processing: {task_id}")
        
        from app.services.video_service import VideoService
        
        # 执行视频生成
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result_task = loop.run_until_complete(
                VideoService.generate_video(db, user_id, request_data)
            )
        finally:
            loop.close()
        
        # 保存历史记录
        if result_task.status == "completed" and result_task.output_data:
            video_url = result_task.output_data.get("video_url")
            if video_url:
                # 生成封面
                thumbnail_url = None
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        thumbnail_url = loop.run_until_complete(
                            VideoService.extract_thumbnail(video_url)
                        )
                    finally:
                        loop.close()
                except Exception as e:
                    print(f"[RQ] 封面生成失败: {e}")
                
                # 去重检查
                existing = db.query(History).filter(
                    History.user_id == user_id,
                    History.url == video_url
                ).first()
                
                if not existing:
                    model = request_data.get("model", "2.6")
                    sound = request_data.get("sound", "off")
                    history = History(
                        user_id=user_id,
                        url=video_url,
                        type=f"视频生成-{model}{'有声' if sound == 'native' else '无声'}",
                        thumbnail=thumbnail_url,
                        created_at=datetime.datetime.utcnow()
                    )
                    db.add(history)
                    db.commit()
                    print(f"[RQ] 历史记录已保存: {video_url}")
        
        print(f"[RQ] 任务完成: task_id={task_id}, status={result_task.status}")
        return {"task_id": task_id, "status": result_task.status}
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"[RQ] 任务失败: task_id={task_id}, error={error_msg}")
        print(f"[RQ] 错误详情: {traceback.format_exc()}")
        
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = "failed"
                task.error_message = error_msg
                db.commit()
        except Exception as e2:
            print(f"[RQ] 更新失败状态时出错: {e2}")
        
        return {"task_id": task_id, "status": "failed", "error": error_msg}
    
    finally:
        db.close()