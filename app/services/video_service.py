"""
视频生成服务
"""
from typing import Optional, Dict
from sqlalchemy.orm import Session
from app.models.task import Task
from app.services.oss_service import oss_service  # 新增：导入 OSS 服务


class VideoService:
    """视频生成服务"""

    @staticmethod
    async def generate_video(db: Session, user_id: int, request_data: Dict) -> Task:
        """
        生成视频 - 调用真实可灵API
        """
        from app.services.kling import kling_service
        
        print("[DEBUG] ========== 开始生成视频 ==========")
        
        # 创建任务
        task = Task(
            user_id=user_id,
            task_type="video_gen",
            status="processing",
            input_data=request_data,
            progress=0
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        print(f"[DEBUG] 视频任务创建成功，ID: {task.id}")
        
        try:
            # 获取图片 URL
            image_url = request_data.get("image_url", "")
            print(f"[DEBUG] 使用图片 URL: {image_url}")
            prompt = request_data.get("prompt", "")
            duration = request_data.get("duration", 5)
            mode = request_data.get("mode", "std")
            
            print(f"[DEBUG] 调用可灵视频API...")
            print(f"[DEBUG] prompt: {prompt}")
            print(f"[DEBUG] duration: {duration}s, mode: {mode}")
            print(f"[DEBUG] 图片 URL: {image_url}")
            
            # 调用可灵API
            api_task_id = kling_service.generate_video(
                image_url=image_url,
                prompt=prompt,
                duration=duration,
                mode=mode
            )
            print(f"[DEBUG] 可灵视频API返回任务ID: {api_task_id}")
            
            # 轮询等待结果
            result = kling_service.wait_for_video_result(api_task_id, max_wait=300)
            
            # 提取视频URL
            video_url = result.get("task_result", {}).get("video_url", "")
            print(f"[DEBUG] 视频URL: {video_url}")
            
            # ========== 上传视频到 OSS ==========
            if video_url:
                try:
                    oss_video_url = await oss_service.upload_file_from_url(
                        video_url,
                        "mp4",
                        "videos"
                    )
                    print(f"[DEBUG] 视频已上传到 OSS: {oss_video_url}")
                    video_url = oss_video_url  # 替换成 OSS URL
                except Exception as e:
                    print(f"[DEBUG] OSS 上传失败，使用原始 URL: {e}")
            # ========== OSS 上传结束 ==========
            
            output_data = {
                "task_id": api_task_id,
                "video_url": video_url,
                "status": "completed"
            }
            
            task.status = "completed"
            task.progress = 100
            task.output_data = output_data
            db.commit()
            print("[DEBUG] ========== 视频生成成功 ==========")
            
        except Exception as e:
            import traceback
            print(f"[DEBUG] 视频生成错误: {e}")
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