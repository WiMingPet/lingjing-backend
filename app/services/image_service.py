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
            request_data: 请求数据 {prompt, negative_prompt, width, height, num_images, reference_image_id, reference_image_url}

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
            # 提取请求参数
            prompt = request_data.get("prompt", "")
            negative_prompt = request_data.get("negative_prompt", "")
            width = request_data.get("width", 512)
            height = request_data.get("height", 512)
            num_images = request_data.get("num_images", 1)
            reference_image_url = request_data.get("reference_image_url", None)  # 新增：获取参考图 URL
            
            print(f"[DEBUG] 调用可灵API生成图片...")
            print(f"[DEBUG] prompt: {prompt}")
            print(f"[DEBUG] negative_prompt: {negative_prompt}")
            print(f"[DEBUG] width: {width}, height: {height}")
            print(f"[DEBUG] 参考图 URL: {reference_image_url}")
            
            # 调用可灵API（支持参考图）
            api_task_id = kling_service.generate_image(
                prompt=prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                num_images=num_images,
                reference_image_url=reference_image_url  # 新增：传递参考图 URL
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
                
                # 添加AI水印到生成的图片
                real_url = await ImageService.add_watermark_to_image(real_url)
                print(f"[DEBUG] 图片水印已添加: {real_url}")
                
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
            import traceback
            traceback.print_exc()
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

    @staticmethod
    async def add_watermark_to_image(image_url: str, text: str = "AI生成") -> str:
        """在图片右下角添加文字水印，返回新的图片URL"""
        import aiohttp
        import tempfile
        import os
        from PIL import Image, ImageDraw, ImageFont
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    image_data = await resp.read()
            
            tmp_input = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            tmp_input.write(image_data)
            tmp_input.close()
            
            img = Image.open(tmp_input.name)
            draw = ImageDraw.Draw(img)
            
            # 字体大小根据图片宽度自适应
            font_size = max(img.width // 20, 14)
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", font_size)
            except:
                font = ImageFont.load_default()
            
            # 文字位置：右下角
            text_bbox = draw.textbbox((0, 0), text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            x = img.width - text_width - 10
            y = img.height - text_height - 10
            
            # 半透明背景
            draw.rectangle([x-5, y-5, x+text_width+5, y+text_height+5], fill=(0, 0, 0, 128))
            draw.text((x, y), text, fill=(255, 255, 255), font=font)
            
            tmp_output = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            tmp_output.close()
            img.save(tmp_output.name, "JPEG")
            
            from app.services.oss_service import oss_service
            with open(tmp_output.name, "rb") as f:
                result_url = await oss_service.upload_file(f.read(), "jpg", "watermarked_images")
            
            os.unlink(tmp_input.name)
            os.unlink(tmp_output.name)
            
            return result_url
            
        except Exception as e:
            print(f"[ERROR] 图片添加水印失败: {e}")
            return image_url