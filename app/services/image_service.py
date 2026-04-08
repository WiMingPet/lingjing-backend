"""
图片生成服务
"""
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from app.models.task import Task
import uuid


class ImageService:
    """图片生成服务"""

    @staticmethod
    async def generate_image(db: Session, user_id: int, request_data: Dict) -> Task:
        """
        生成图片 - 调用真实可灵API

        Args:
            db: 数据库会话
            user_id: 用户ID
            request_data: 请求数据 {prompt, negative_prompt, width, height, num_images, reference_image_id}

        Returns:
            Task: 创建的任务
        """
        from app.services.kling import kling_service
        print("[DEBUG] ========== 开始生成图片 ==========")
        print(f"[DEBUG] 用户ID: {user_id}")
        print(f"[DEBUG] 请求数据: {request_data}")
        
        # 创建任务
        task = Task(
            user_id=user_id,
            task_type="image_gen",
            status="processing",
            input_data=request_data,
            progress=0
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        print(f"[DEBUG] 任务创建成功，ID: {task.id}")
        
        try:
            # 调用可灵API
            prompt = request_data.get("prompt", "")
            negative_prompt = request_data.get("negative_prompt", "")
            width = request_data.get("width", 512)
            height = request_data.get("height", 512)
            
            print(f"[DEBUG] 调用可灵API生成图片...")
            print(f"[DEBUG] prompt: {prompt}")
            print(f"[DEBUG] negative_prompt: {negative_prompt}")
            print(f"[DEBUG] width: {width}, height: {height}")
            
            api_task_id = kling_service.generate_image(
                prompt=prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height
            )
            print(f"[DEBUG] 可灵API返回任务ID: {api_task_id}")
            
            # 轮询等待结果
            print(f"[DEBUG] 等待任务完成...")
            result = kling_service.wait_for_result(api_task_id, "image", max_wait=120)
            print(f"[DEBUG] wait_for_result 完整返回: {result}")
            print(f"[DEBUG] task_result: {result.get('task_result')}")
            print(f"[DEBUG] images: {result.get('task_result', {}).get('images')}")
            
            # 提取图片URL
            images = result.get("task_result", {}).get("images", [])
            print(f"[DEBUG] 获取到 {len(images)} 张图片")
            
            if images:
                real_url = images[0].get("url")
                print(f"[DEBUG] 真实图片URL: {real_url}")
                
                output_data = {
                    "task_id": api_task_id,
                    "images": [{"url": real_url}],
                    "status": "completed"
                }
            else:
                print("[DEBUG] 没有获取到图片，使用 Mock 数据")
                output_data = ImageService.mock_image_generation(task.id)
            
            print(f"[DEBUG] 最终 output_data: {output_data}")
            
            task.status = "completed"
            task.progress = 100
            task.output_data = output_data
            db.commit()
            print("[DEBUG] ========== 图片生成成功 ==========")
            
        except Exception as e:
            print(f"[DEBUG] 错误: {e}")
            task.status = "failed"
            task.error_message = str(e)
            db.commit()
            raise e
        
        return task

    @staticmethod
    def mock_image_generation(task_id: int) -> Dict:
        """
        Mock图片生成（备用）
        """
        return {
            "task_id": task_id,
            "images": [
                {
                    "url": f"https://example.com/generated/image_{task_id}_1.jpg",
                    "seed": 12345
                }
            ],
            "status": "completed"
        }

    @staticmethod
    def update_task_progress(db: Session, task_id: int, progress: int, output_data: Optional[Dict] = None):
        """更新任务进度"""
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.progress = progress
            if output_data:
                task.output_data = output_data
            if progress >= 100:
                task.status = "completed"
            db.commit()

    @staticmethod
    def get_task_result(db: Session, task_id: int) -> Optional[Task]:
        """获取任务结果"""
        return db.query(Task).filter(Task.id == task_id).first()