"""
多角度试穿服务
"""
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from app.models.task import Task


class MultiAngleService:
    """多角度试穿服务"""

    @staticmethod
    async def generate_unified_character(db: Session, user_id: int, request_data: Dict) -> Task:
        """
        多图参考合成统一角色
        """
        from app.services.kling import kling_service
        
        print("[DEBUG] ========== 开始多角度合成 ==========")
        
        # 创建任务
        task = Task(
            user_id=user_id,
            task_type="multi_angle",
            status="processing",
            input_data=request_data,
            progress=0
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        print(f"[DEBUG] 多角度任务创建成功，ID: {task.id}")
        
        try:
            # 获取参数
            subject_images = request_data.get("subject_images", [])
            prompt = request_data.get("prompt", "A full body photo of a person, consistent appearance")
            scene_image = request_data.get("scene_image", None)
            style_image = request_data.get("style_image", None)
            
            print(f"[DEBUG] 调用可灵多图参考API...")
            print(f"[DEBUG] 主体图片数量: {len(subject_images)}")
            for i, img in enumerate(subject_images):
                print(f"[DEBUG] 图片{i+1}: {img}")
            print(f"[DEBUG] prompt: {prompt}")
            
            # 调用可灵API
            api_task_id = kling_service.multi_image_to_image(
                subject_images=subject_images,
                prompt=prompt,
                scene_image=scene_image,
                style_image=style_image
            )
            print(f"[DEBUG] 可灵多图参考API返回任务ID: {api_task_id}")
            
            # 轮询等待结果
            result = kling_service.wait_for_multi_image_result(api_task_id, max_wait=120)
            
            # 提取生成的图片URL
            images = result.get("task_result", {}).get("images", [])
            if images:
                character_image_url = images[0].get("url", "")
            else:
                character_image_url = ""
            
            print(f"[DEBUG] 合成角色图片URL: {character_image_url}")
            
            output_data = {
                "task_id": api_task_id,
                "character_image_url": character_image_url,
                "status": "completed"
            }
            
            task.status = "completed"
            task.progress = 100
            task.output_data = output_data
            db.commit()
            print("[DEBUG] ========== 多角度合成成功 ==========")
            
        except Exception as e:
            import traceback
            print(f"[DEBUG] 多角度合成错误: {e}")
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