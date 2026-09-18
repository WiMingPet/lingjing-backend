"""
套图生成 RQ 任务
"""
import asyncio
import datetime
import json
from app.database import SessionLocal
from app.models.task import Task
from app.models.history import History
from app.utils.refund import refund_credits


def generate_suite_task(task_id: int, user_id: int, request_data: dict):
    """后台执行套图生成"""
    print(f"[RQ-SUITE] 开始: task_id={task_id}")
    
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return {"error": "任务不存在"}
        
        task.status = "processing"
        db.commit()
        
        from app.services.suite_generator import suite_generator
        
        suite_type = request_data.get("suite_type")
        cloth_url = request_data.get("cloth_url")
        analysis = request_data.get("analysis", {})
        scene_count = request_data.get("scene_count", 4)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if suite_type == "white_bg":
                images = loop.run_until_complete(
                    suite_generator.generate_white_bg(cloth_url)
                )
            elif suite_type == "scene":
                images = loop.run_until_complete(
                    suite_generator.generate_scene_images(cloth_url, analysis, scene_count)
                )
            elif suite_type == "aplus":
                aplus_count = request_data.get("aplus_count", 2)
                images = loop.run_until_complete(
                    suite_generator.generate_aplus_images(cloth_url, analysis, aplus_count)
                )
            else:
                raise Exception(f"无效的套图类型: {suite_type}")
        finally:
            loop.close()
        
        if not images:
            raise Exception("套图生成失败，未获取到图片")
        
        # ========== images 现在是 List[dict]，每个含 watermarked 和 clean ==========
        task.status = "completed"
        task.output_data = {"images": images, "analysis": analysis, "history_id": 0}
        task.progress = 100
        task.completed_at = datetime.datetime.utcnow()
        db.commit()

        history = History(
            user_id=user_id,
            url=json.dumps(images),
            type="电商商品套图",
            thumbnail=images[0]["watermarked"] if images else None,
            created_at=datetime.datetime.utcnow()
        )
        db.add(history)
        db.commit()
        db.refresh(history)

        task.output_data = {"images": images, "analysis": analysis, "history_id": history.id}
        db.commit()
        
        print(f"[RQ-SUITE] 完成: task_id={task_id}, 生成 {len(images)} 张图")
        return {"task_id": task_id, "status": "completed", "images": images}
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"[RQ-SUITE] 失败: task_id={task_id}, error={error_msg}")
        print(traceback.format_exc())
        
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = "failed"
                task.error_message = error_msg
                db.commit()
        except Exception as e2:
            print(f"[RQ-SUITE] 更新失败状态出错: {e2}")
        
        refund_credits(db, task_id, reason=f"套图生成失败: {error_msg}")
        return {"task_id": task_id, "status": "failed", "error": error_msg}
    
    finally:
        db.close()