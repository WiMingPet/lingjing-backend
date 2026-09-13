import asyncio
import datetime
from app.database import SessionLocal
from app.models.task import Task
from app.utils.refund import refund_credits


def generate_image_task(task_id: int, user_id: int, request_data: dict):
    """后台执行图片生成"""
    print(f"[RQ-IMAGE] 开始: task_id={task_id}, user_id={user_id}")
    
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return {"error": "任务不存在"}
        
        task.status = "processing"
        db.commit()
        
        from app.services.image_service import ImageService
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result_task = loop.run_until_complete(
                ImageService.generate_image(db, user_id, request_data)
            )
        finally:
            loop.close()
        
        # ========== 同步内层 task 的结果到外层 task ==========
        outer_task = db.query(Task).filter(Task.id == task_id).first()
        if outer_task:
            outer_task.status = result_task.status
            outer_task.output_data = result_task.output_data
            outer_task.progress = 100
            outer_task.completed_at = datetime.datetime.utcnow()
            db.commit()
            print(f"[RQ-IMAGE] 外层任务已同步: task_id={task_id}, status={result_task.status}")
            
            # ========== 如果内层失败，退款 ==========
            if result_task.status == "failed":
                refund_credits(
                    db, task_id, 
                    reason=f"图片生成失败: {result_task.error_message or '未知错误'}"
                )
            # ============================================
        # ========================================================
        
        print(f"[RQ-IMAGE] 完成: task_id={task_id}")
        return {"task_id": task_id, "status": result_task.status}
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"[RQ-IMAGE] 失败: task_id={task_id}, error={error_msg}")
        print(traceback.format_exc())
        
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = "failed"
                task.error_message = error_msg
                db.commit()
        except Exception as e2:
            print(f"[RQ-IMAGE] 更新失败状态出错: {e2}")
        
        refund_credits(db, task_id, reason=f"图片生成失败: {error_msg}")
        return {"task_id": task_id, "status": "failed", "error": error_msg}
    
    finally:
        db.close()