"""
视频生成服务
"""
from typing import Optional, Dict
from sqlalchemy.orm import Session
from app.models.task import Task
from app.services.oss_service import oss_service  # 新增：导入 OSS 服务
from fastapi import HTTPException


class VideoService:
    """视频生成服务"""

    @staticmethod
    async def generate_video(db: Session, user_id: int, request_data: Dict) -> Task:
        """
        生成视频 - 调用2.6基础版或3.0增强版API
        """
        from app.services.kling import kling_service
        from app.services.image_service import ImageService
        
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
            
            # 图片安全审核
            from app.services.image_service import ImageService
            if not await ImageService.check_image_safety(image_url):
                raise HTTPException(status_code=400, detail="图片未通过安全审核，请更换图片")
            
            prompt = request_data.get("prompt", "")
            duration = request_data.get("duration", 5)
            mode = request_data.get("mode", "std")

            # ========== 获取并验证模型参数 ==========
            model = request_data.get("model", "2.6")
            sound = request_data.get("sound", "off")
            print(f"[DEBUG] 模型: {model}, 声音: {sound}")
            
            # 验证模型
            if model not in ["2.6", "3.0"]:
                raise HTTPException(status_code=400, detail="无效的模型选择")
            
            # 验证声音模式
            if sound not in ["off", "native"]:
                raise HTTPException(status_code=400, detail="无效的声音模式")
            
            # 2.6模型限制
            if model == "2.6":
                if sound != "off":
                    raise HTTPException(status_code=400, detail="2.6基础版仅支持无声视频")
                if duration not in [5, 10]:
                    raise HTTPException(status_code=400, detail="2.6基础版仅支持5秒或10秒")
            else:
                # 3.0模型限制
                if duration not in [5, 10, 15]:
                    raise HTTPException(status_code=400, detail="3.0增强版支持5秒、10秒或15秒")
            # ================================================
            
            # 内容安全审核
            if not ImageService._check_prompt_safety(prompt):
                task.status = "failed"
                task.error_message = "提示词包含不当内容，请修改后重试"
                db.commit()
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail="您输入的提示词不符合平台规范，请修改后重试")

            print(f"[DEBUG] 调用可灵视频API...")
            print(f"[DEBUG] model: {model}, sound: {sound}")
            print(f"[DEBUG] prompt: {prompt}")
            print(f"[DEBUG] duration: {duration}s, mode: {mode}")
            print(f"[DEBUG] 图片 URL: {image_url}")
            
            # 调用可灵API（传入模型和声音参数）
            api_task_id = kling_service.generate_video(
                image_url=image_url,
                prompt=prompt,
                duration=duration,
                mode=mode,
                model=model,
                sound=sound
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
                    video_url = oss_video_url
                except Exception as e:
                    print(f"[DEBUG] OSS 上传失败，使用原始 URL: {e}")
            # ========== OSS 上传结束 ==========
            
            output_data = {
                "task_id": api_task_id,
                "video_url": video_url,
                "status": "completed",
                "model": model,
                "sound": sound,
                "duration": duration
            }
            
            task.status = "completed"
            task.progress = 100
            task.output_data = output_data
            db.commit()
            print("[DEBUG] ========== 视频生成成功 ==========")
            
        except Exception as e:
            import traceback
            error_msg = str(e)
            if "risk control" in error_msg:
                error_msg = "内容未通过安全审核，请更换图片后重试"
            print(f"[DEBUG] 视频生成错误: {e}")
            print(f"[DEBUG] 错误详情: {traceback.format_exc()}")
            task.status = "failed"
            task.error_message = error_msg
            db.commit()
            raise HTTPException(status_code=400, detail=error_msg)
        
        return task

    @staticmethod
    def get_task_result(db: Session, task_id: int) -> Optional[Task]:
        """获取任务结果"""
        return db.query(Task).filter(Task.id == task_id).first()

    @staticmethod
    async def extract_thumbnail(video_url: str) -> Optional[str]:
        """
        从视频URL提取第一帧并上传到OSS，返回封面图URL。
        若失败返回 None。
        """
        import subprocess
        import tempfile
        import os

        # 1. 下载视频到临时文件
        tmp_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp_video.close()
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(video_url) as resp:
                    if resp.status != 200:
                        print(f"[DEBUG] 下载视频失败: HTTP {resp.status}")
                        return None
                    with open(tmp_video.name, "wb") as f:
                        f.write(await resp.read())
        except Exception as e:
            print(f"[DEBUG] 下载视频异常: {e}")
            if os.path.exists(tmp_video.name):
                os.unlink(tmp_video.name)
            return None

        # 2. 用 ffmpeg 提取第一帧到临时文件
        tmp_thumbnail = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp_thumbnail.close()
        try:
            cmd = [
                "ffmpeg", "-i", tmp_video.name,
                "-ss", "00:00:01.000",
                "-vframes", "1",
                tmp_thumbnail.name,
                "-y"
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except Exception as e:
            print(f"[DEBUG] ffmpeg 提取封面失败: {e}")
            if os.path.exists(tmp_thumbnail.name):
                os.unlink(tmp_thumbnail.name)
            return None
        finally:
            # 删除临时视频
            if os.path.exists(tmp_video.name):
                os.unlink(tmp_video.name)

        # 3. 上传封面到OSS（读取文件字节）
        if os.path.exists(tmp_thumbnail.name) and os.path.getsize(tmp_thumbnail.name) > 0:
            try:
                with open(tmp_thumbnail.name, "rb") as f:
                    thumbnail_bytes = f.read()
                oss_url = await oss_service.upload_file(
                    file_content=thumbnail_bytes,
                    file_extension="jpg",
                    sub_folder="thumbnails"
                )
                os.unlink(tmp_thumbnail.name)
                return oss_url
            except Exception as e:
                print(f"[DEBUG] 上传封面到OSS失败: {e}")
                if os.path.exists(tmp_thumbnail.name):
                    os.unlink(tmp_thumbnail.name)
                return None
        else:
            print("[DEBUG] 提取的封面文件不存在或为空")
            return None