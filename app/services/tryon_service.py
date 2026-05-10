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
        生成虚拟试穿视频 - 先调用可灵图生图接口生成试穿效果图，再调用图生视频接口生成动态展示视频
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
            
            print(f"[DEBUG] 第一步：调用可灵虚拟试穿API生成效果图...")
            print(f"[DEBUG] 模特图片URL: {model_image_url}")
            print(f"[DEBUG] 服装图片URL: {garment_image_url}")
            
            # 1. 调用可灵虚拟试穿图生图接口
            # 根据产品标题自动判断服装类别
            def _detect_cloth_category(title: str) -> str:
                title_lower = title.lower()
                # 下装关键词
                if any(kw in title_lower for kw in [
                    "裤", "裙", "短裤", "长裤", "阔腿裤", "牛仔裤", "休闲裤",
                    "热裤", "牛仔短裤", "牛仔长裤", "半身裙", "百褶裙", "包臀裙",
                    "下装", "裤子", "五分裤", "七分裤", "九分裤", "直筒裤", "工装裤"
                ]):
                    return "lower"
                # 连衣裙/套装关键词
                if any(kw in title_lower for kw in ["连衣裙", "套装", "连体", "裙子", "长裙", "短裙"]):
                    return "dress"
                # 上装关键词
                if any(kw in title_lower for kw in ["衣", "T恤", "衬衫", "外套", "卫衣", "夹克", "羽绒", "马甲", "背心", "毛衣", "针织"]):
                    return "upper"
                # 默认
                return "dress"
            
            cloth_category = request_data.get("cloth_category") or _detect_cloth_category(request_data.get("title", ""))
            print(f"[DEBUG] 自动识别服装类别: {cloth_category}")
            
            # 套装/组合产品使用专用模特图
            title = request_data.get("title", "")
            combo_keywords = ["套装", "搭配", "套", "组合", "配", "两件套", "三件套", "上衣", "衬衫", "T恤", "卫衣", "外套", "夹克", "羽绒", "马甲", "背心", "毛衣", "针织", "衣", "连体", "连衣裙"]
            if any(kw in title for kw in combo_keywords):
                cloth_category = None
                model_image_url = "https://media.lingjing-media.com/%E5%AE%B6%E9%A6%A8.png"
                print(f"[DEBUG] 检测到套装/组合产品，不传cloth_category，让可灵自动识别")
            
            api_task_id = kling_service.generate_tryon(
                human_image_url=model_image_url,
                cloth_image_url=garment_image_url,
                cloth_category=cloth_category,
                digital_human_id=digital_human_id
            )
            print(f"[DEBUG] 可灵虚拟试穿API返回任务ID: {api_task_id}")
            
            # 轮询等待试穿结果图片
            result = kling_service.wait_for_tryon_result(api_task_id, max_wait=120)
            
            # 提取试穿效果图片URL
            images = result.get("task_result", {}).get("images", [])
            if images:
                tryon_image_url = images[0].get("url", "")
                print(f"[DEBUG] 试穿效果图: {tryon_image_url}")
            else:
                raise Exception("虚拟试穿未返回效果图")
            
            task.progress = 50
            db.commit()
            
            # 2. 用试穿效果图生成动态展示视频
            print(f"[DEBUG] 第二步：调用可灵图生视频接口生成动态展示...")
            
            video_prompt = "模特全身入镜，自然站立。先正面展示3秒，然后用手轻轻捏起衣角展示面料细节，接着缓慢旋转360度展示全身服装各角度，包括上衣、裤子、背面。最后恢复正面站姿。整个过程自然流畅，专业灯光，4K高清"
            
            video_task_id = kling_service.generate_video(
                image_url=tryon_image_url,
                prompt=video_prompt,
                duration=5,
                mode="std"
            )
            print(f"[DEBUG] 图生视频任务ID: {video_task_id}")
            
            # 轮询等待视频生成
            video_result = kling_service.wait_for_video_result(video_task_id, max_wait=300)
            video_url = video_result.get("task_result", {}).get("video_url", "")
            
            if not video_url:
                # 如果视频生成失败，降级使用图片
                print("[DEBUG] 视频生成失败，降级使用效果图")
                video_url = tryon_image_url
            
            print(f"[DEBUG] 试穿展示视频: {video_url}")
            
            output_data = {
                "task_id": api_task_id,
                "video_task_id": video_task_id,
                "video_url": video_url,
                "tryon_image_url": tryon_image_url,
                "status": "completed"
            }
            
            task.status = "completed"
            task.progress = 100
            task.output_data = output_data
            db.commit()
            print("[DEBUG] ========== 虚拟试穿完成 ==========")
            
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