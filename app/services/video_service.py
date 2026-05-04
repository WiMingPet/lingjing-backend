"""
视频生成服务
"""
from typing import Optional, Dict
from sqlalchemy.orm import Session
from app.models.task import Task
from app.services.oss_service import oss_service  # 新增：导入 OSS 服务
import subprocess
import tempfile
import os
import requests
import time


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
            
            # ========== 提取封面图并保存历史记录 ==========
            thumbnail_url = None
            if video_url:
                thumbnail_url = await VideoService.extract_thumbnail(video_url)
                print(f"[DEBUG] 封面图URL: {thumbnail_url}")
                
                # 保存到历史记录表
                from app.models.history import History
                history = History(
                    user_id=user_id,
                    url=video_url,
                    type="视频生成",
                    thumbnail=thumbnail_url
                )
                db.add(history)
                print(f"[DEBUG] 历史记录已保存，用户ID: {user_id}")
            # =============================================
            
            output_data = {
                "task_id": api_task_id,
                "video_url": video_url,
                "status": "completed",
                "thumbnail_url": thumbnail_url   # 添加封面图到返回数据
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
    async def extract_thumbnail(video_url: str) -> str:
        """下载视频，提取第一帧为jpg，上传OSS，返回封面图URL"""
        from app.services.oss_service import oss_service
        
        temp_files = []
        try:
            # 1. 下载视频
            resp = requests.get(video_url, timeout=30)
            resp.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                f.write(resp.content)
                video_path = f.name
                temp_files.append(video_path)
            
            # 2. 提取第一帧
            thumb_path = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name
            temp_files.append(thumb_path)
            subprocess.run([
                'ffmpeg', '-i', video_path, '-vframes', '1',
                '-q:v', '2', '-y', thumb_path
            ], check=True, capture_output=True)
            
            # 3. 上传到OSS
            with open(thumb_path, 'rb') as f:
                thumb_url = await oss_service.upload_file(
                    f.read(),
                    f"thumbnails/video_{int(time.time())}.jpg",
                    "history"
                )
            return thumb_url
        except Exception as e:
            print(f"[DEBUG] 提取封面失败: {e}")
            return None
        finally:
            for path in temp_files:
                if os.path.exists(path):
                    try:
                        os.unlink(path)
                    except:
                        pass

    @staticmethod
    def get_task_result(db: Session, task_id: int) -> Optional[Task]:
        """获取任务结果"""
        return db.query(Task).filter(Task.id == task_id).first()