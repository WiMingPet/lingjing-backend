"""
尺码推荐服务
"""
from typing import Optional, Dict
from sqlalchemy.orm import Session
from app.models.task import Task
from app.services.size_estimator_mediapipe import size_estimator


class SizeService:
    """尺码推荐服务"""

    @staticmethod
    async def recommend_size(db: Session, user_id: int, image_path: str, height_cm: float = 170.0, oss_url: str = None) -> Task:
        """
        从图片推荐尺码
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            image_path: 本地图片路径（用于 MediaPipe 处理）
            height_cm: 用户身高（厘米）
            oss_url: OSS 公网 URL（用于存储和展示）
        """
        print("[DEBUG] ========== 开始尺码推荐 ==========")
        
        # 创建任务，保存 OSS URL
        task = Task(
            user_id=user_id,
            task_type="size_recommend",
            status="processing",
            input_data={"image_url": oss_url, "height_cm": height_cm},
            progress=0
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        print(f"[DEBUG] 尺码推荐任务创建成功，ID: {task.id}")
        
        try:
            # 调用尺寸估算（传入本地文件路径）
            result = size_estimator.estimate_from_image(image_path, height_cm)
            
            if not result.get("success"):
                raise Exception(result.get("error", "估算失败"))
            
            output_data = {
                "bust": result["bust"],
                "waist": result["waist"],
                "hip": result["hip"],
                "shoulder_width": result["shoulder_width"],
                "recommended_size": result["recommended_size"],
                "confidence": result["confidence"],
                "image_url": oss_url  # 添加 OSS URL 到输出
            }
            
            task.status = "completed"
            task.progress = 100
            task.output_data = output_data
            db.commit()
            print("[DEBUG] ========== 尺码推荐成功 ==========")
            
        except Exception as e:
            import traceback
            print(f"[DEBUG] 尺码推荐错误: {e}")
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