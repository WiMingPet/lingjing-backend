"""
口播带货 RQ 任务
"""
import asyncio
import datetime
from app.database import SessionLocal
from app.models.task import Task
from app.models.history import History
from app.models.user import User
from app.utils.refund import refund_credits
from app.data.prices import TALKING_AGENT_COST_PER_SECOND


def generate_talking_agent_task(task_id: int, user_id: int, request_data: dict):
    """后台执行口播带货生成"""
    print(f"[RQ-TALKING] 开始: task_id={task_id}, user_id={user_id}")
    
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return {"error": "任务不存在"}
        
        task.status = "processing"
        db.commit()
        
        from app.services.kling import kling_service
        
        # 同步调用
        result = kling_service.generate_talking_agent(request_data)
        
        video_url = result.get("video_url")
        actual_duration = float(result.get("duration", 0))
        
        if not video_url:
            raise Exception("口播视频生成失败，未获取到视频链接")
        
        # ========== 转存视频到 OSS ==========
        try:
            from app.services.oss_service import oss_service
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                oss_video_url = loop.run_until_complete(
                    oss_service.upload_file_from_url(video_url, "mp4", "talking_agent")
                )
            finally:
                loop.close()
            print(f"[RQ-TALKING] 视频已转存 OSS: {oss_video_url}")
            video_url = oss_video_url
        except Exception as e:
            print(f"[RQ-TALKING] OSS 转存失败，使用原始 URL: {e}")
        # ==================================
        
        # ========== 结算：只退款，不补扣 ==========
        actual_cost = int(actual_duration * TALKING_AGENT_COST_PER_SECOND)
        estimated_cost = task.credits_cost
        refund_amount = 0
        
        if actual_cost < estimated_cost:
            refund_amount = estimated_cost - actual_cost
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.credits += refund_amount
                task.credits_cost = actual_cost
                db.commit()
                print(f"[RQ-TALKING] 退款差额: {refund_amount} 点，实际费用: {actual_cost} 点")
        else:
            print(f"[RQ-TALKING] 实际费用 {actual_cost} 点 ≥ 预扣 {estimated_cost} 点，不补扣")
        # ========================================
        
        # 提取封面
        thumbnail_url = None
        try:
            from app.services.video_service import VideoService
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                thumbnail_url = loop.run_until_complete(
                    VideoService.extract_thumbnail(video_url)
                )
            finally:
                loop.close()
        except Exception as e:
            print(f"[RQ-TALKING] 封面生成失败: {e}")
        
        # 更新任务
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
        
        # 保存历史记录
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
        
        print(f"[RQ-TALKING] 完成: task_id={task_id}, 时长={actual_duration}秒")
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
        
        refund_credits(db, task_id, reason=f"口播带货失败: {error_msg}")
        return {"task_id": task_id, "status": "failed", "error": error_msg}
    
    finally:
        db.close()