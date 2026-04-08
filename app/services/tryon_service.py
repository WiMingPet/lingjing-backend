"""
虚拟试穿服务
"""
from typing import Optional, Dict
from sqlalchemy.orm import Session
from app.models.task import Task


class TryonService:
    """虚拟试穿服务"""

    @staticmethod
    async def generate_tryon(db: Session, user_id: int, request_data: Dict) -> Task:
        """
        生成虚拟试穿图片 - 调用真实可灵API
        """
        from app.services.kling import kling_service
        
        print("[DEBUG] ========== 开始虚拟试穿 ==========")
        
        # 创建任务
        task = Task(
            user_id=user_id,
            task_type="tryon",
            status="processing",
            input_data=request_data,
            progress=0
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        print(f"[DEBUG] 虚拟试穿任务创建成功，ID: {task.id}")
        
        try:
            # 获取参数
            model_image_url = request_data.get("model_image_url", "")
            garment_image_url = request_data.get("garment_image_url", "")
            digital_human_id = request_data.get("digital_human_id", None)
            
            print(f"[DEBUG] 调用可灵虚拟试穿API...")
            print(f"[DEBUG] 模特图片URL: {model_image_url}")
            print(f"[DEBUG] 服装图片URL: {garment_image_url}")
            
            # 调用可灵API
            api_task_id = kling_service.generate_tryon(
                model_image_url=model_image_url,
                garment_image_url=garment_image_url,
                digital_human_id=digital_human_id
            )
            print(f"[DEBUG] 可灵虚拟试穿API返回任务ID: {api_task_id}")
            
            # 轮询等待结果
            result = kling_service.wait_for_tryon_result(api_task_id, max_wait=120)
            
            # 提取结果（虚拟试穿返回的是图片）
            images = result.get("task_result", {}).get("images", [])
            if images:
                image_url = images[0].get("url", "")
                # 可灵返回的是图片URL，这里存入 video_url 字段
                video_url = image_url
            else:
                video_url = ""
            
            print(f"[DEBUG] 试穿结果图片URL: {video_url}")
            
            output_data = {
                "task_id": api_task_id,
                "video_url": video_url,
                "status": "completed"
            }
            
            task.status = "completed"
            task.progress = 100
            task.output_data = output_data
            db.commit()
            print("[DEBUG] ========== 虚拟试穿成功 ==========")
            
        except Exception as e:
            import traceback
            print(f"[DEBUG] 虚拟试穿错误: {e}")
            print(f"[DEBUG] 错误详情: {traceback.format_exc()}")
            task.status = "failed"
            task.error_message = str(e)
            db.commit()
            raise e
        
        return task

    @staticmethod
    def get_task_result(db: Session, task_id: int) -> Optional[Task]:
        """获取任务结果"""
        return db.query(Task).filter(Task.id == task_id).first()