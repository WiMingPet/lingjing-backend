import asyncio
import datetime
from app.database import SessionLocal
from app.models.task import Task
from app.models.history import History
from app.utils.refund import refund_credits


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def generate_tryon_task(task_id: int, user_id: int, request_data: dict):
    return _generic_task(task_id, user_id, request_data, "tryon", "虚拟试穿")


def generate_multi_angle_task(task_id: int, user_id: int, request_data: dict):
    return _generic_task(task_id, user_id, request_data, "multi_angle", "多角度试穿")


def generate_digital_human_task(task_id: int, user_id: int, request_data: dict):
    return _generic_task(task_id, user_id, request_data, "digital_human", "数字人分身")


def generate_ecommerce_video_task(task_id: int, user_id: int, request_data: dict):
    return _generic_task(task_id, user_id, request_data, "ecommerce", "AI带货视频")


def generate_merchant_task(task_id: int, user_id: int, request_data: dict):
    return _generic_task(task_id, user_id, request_data, "merchant", "电商商品套图")


def _generic_task(task_id, user_id, request_data, task_type, task_name):
    print(f"[RQ-OTHER] 开始 {task_name}: task_id={task_id}, user_id={user_id}")
    
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return {"error": "任务不存在"}
        
        task.status = "processing"
        db.commit()
        
        # 根据任务类型调用对应服务
        if task_type == "tryon":
            from app.services.tryon_service import TryonService
            _run_async(TryonService.generate_tryon(db, user_id, request_data))
        
        elif task_type == "multi_angle":
            from app.services.kling import kling_service
            from app.services.oss_service import oss_service
            import subprocess
            import tempfile
            import aiohttp
            
            image_urls = request_data.get("image_urls", [])
            description = request_data.get("description", "")
            
            if len(image_urls) < 2 or len(image_urls) > 4:
                raise Exception("请上传2-4张不同角度的照片")
            
            # 1. 为每张图片生成视频
            prompt = f"展示服装多角度细节，{description}，镜头缓慢旋转，专业灯光，4K高清" if description else "展示服装多角度细节，镜头缓慢旋转，专业灯光，4K高清"
            
            video_urls = []
            for i, img_url in enumerate(image_urls):
                print(f"[RQ-OTHER] 生成第{i+1}个角度的视频...")
                api_task_id = kling_service.generate_video(
                    image_url=img_url,
                    prompt=f"{prompt}，第{i+1}个角度",
                    duration=5,
                    mode="std"
                )
                result = kling_service.wait_for_video_result(api_task_id, max_wait=600)
                video_url = result.get("task_result", {}).get("video_url")
                if video_url:
                    video_urls.append(video_url)
            
            if not video_urls:
                raise Exception("所有角度视频生成失败")
            
            # 2. ffmpeg 合并
            print(f"[RQ-OTHER] 开始合并 {len(video_urls)} 个角度视频...")
            final_video_url = _merge_angle_videos_sync(video_urls)
            
            if not final_video_url:
                raise Exception("多角度视频合成失败")
            
            # 3. 提取封面
            thumbnail_url = None
            try:
                from app.services.video_service import VideoService
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    thumbnail_url = loop.run_until_complete(
                        VideoService.extract_thumbnail(final_video_url)
                    )
                finally:
                    loop.close()
            except Exception as e:
                print(f"[RQ-OTHER] 封面提取失败: {e}")
            
            # 4. 更新任务
            task.status = "completed"
            task.output_data = {"video_url": final_video_url, "thumbnail": thumbnail_url}
            db.commit()
            
            # 5. 保存历史记录
            if final_video_url:
                existing = db.query(History).filter(
                    History.user_id == user_id, History.url == final_video_url
                ).first()
                if not existing:
                    history = History(
                        user_id=user_id,
                        url=final_video_url,
                        type="多角度试穿",
                        thumbnail=thumbnail_url,
                        created_at=datetime.datetime.utcnow()
                    )
                    db.add(history)
                    db.commit()
            
            print(f"[RQ-OTHER] 多角度试穿完成: task_id={task_id}")
            return {"task_id": task_id, "status": "completed"}
        
        elif task_type == "digital_human":
            from app.services.kling import kling_service
            api_task_id = _run_async(
                kling_service.generate_digital_human(
                    image_url=request_data.get("image_url"),
                    text=request_data.get("text"),
                    voice=request_data.get("voice"),
                    prompt=request_data.get("prompt"),
                )
            )
            result = kling_service.wait_for_digital_human_result(api_task_id)
            video_url = result.get("task_result", {}).get("video_url", "")
            
            task.status = "completed"
            task.output_data = {"video_url": video_url}
            db.commit()
            
            if video_url:
                existing = db.query(History).filter(
                    History.user_id == user_id, History.url == video_url
                ).first()
                if not existing:
                    history = History(
                        user_id=user_id, url=video_url, type="数字人分身",
                        created_at=datetime.datetime.utcnow()
                    )
                    db.add(history)
                    db.commit()
        
        elif task_type == "ecommerce":
            from app.services.ecommerce_service import EcommerceService
            from app.schemas.ecommerce import ProductInfo, VideoTaskRequest
            
            service = EcommerceService()
            
            # 1. 解析商品
            product = None
            if request_data.get("url"):
                try:
                    product = _run_async(service.parse_product_url(request_data["url"]))
                except Exception as e:
                    print(f"[RQ-OTHER] 解析URL失败: {e}")
            
            if not product:
                product = ProductInfo(
                    title="商品",
                    price="0",
                    description=request_data.get("description") or "",
                    images=[request_data.get("image_url")] if request_data.get("image_url") else [],
                    platform="manual"
                )
            
            is_manual = not request_data.get("url") and (
                request_data.get("image_url") or request_data.get("description")
            )
            
            # 2. 生成文案
            script = _run_async(service.generate_copywriting(product, is_manual_mode=is_manual))
            
            # 3. 生成视频
            result = _run_async(
                service.create_product_video(
                    script,
                    product,
                    digital_image_url=request_data.get("digital_image_url"),
                    digital_human_id=request_data.get("digital_human_id"),
                    user_token=None,
                    is_manual_mode=is_manual
                )
            )
            
            video_url = result.get("video_url")
            if not video_url:
                raise Exception("视频生成失败")
            
            # 4. 生成封面
            thumbnail_url = None
            try:
                from app.services.video_service import VideoService
                thumbnail_url = _run_async(VideoService.extract_thumbnail(video_url))
            except Exception as e:
                print(f"[RQ-OTHER] 封面生成失败: {e}")
            
            # 5. 更新任务
            task.status = "completed"
            task.output_data = {"video_url": video_url, "thumbnail": thumbnail_url}
            db.commit()
            
            # 6. 保存历史记录
            existing = db.query(History).filter(
                History.user_id == user_id,
                History.url == video_url,
                History.type == "AI带货视频"
            ).first()
            
            if not existing:
                history = History(
                    user_id=user_id,
                    url=video_url,
                    type="AI带货视频",
                    thumbnail=thumbnail_url,
                    created_at=datetime.datetime.utcnow()
                )
                db.add(history)
                db.commit()
            
            print(f"[RQ-OTHER] AI带货视频完成: task_id={task_id}")
            return {"task_id": task_id, "status": "completed"}
        
        elif task_type == "merchant":
            from app.routers.merchant import _generate_package_logic
            import json
            
            cloth_urls = request_data.get("cloth_urls", [])
            template = request_data.get("template")
            product_type = request_data.get("product_type", "other")
            height = request_data.get("height")
            weight = request_data.get("weight")
            scene_count = request_data.get("scene_count", 1)
            gender = request_data.get("gender", "female")
            scene_text = request_data.get("scene_text", "")
            
            # 调用核心生成逻辑
            results = _run_async(_generate_package_logic(
                cloth_urls=cloth_urls,
                template=template,
                product_type=product_type,
                height=height,
                weight=weight,
                scene_count=scene_count,
                gender=gender,
                scene_text=scene_text,
            ))
            
            # 更新任务
            task.status = "completed"
            task.output_data = {"results": results}
            db.commit()
            
            # 保存历史记录
            for item in results:
                all_images = []
                all_images.extend(item.get("tryon_images", []))
                all_images.extend(item.get("main_images", []))
                all_images.extend(item.get("scene_images", []))
                
                if all_images:
                    existing = db.query(History).filter(
                        History.user_id == user_id,
                        History.url == json.dumps(all_images)
                    ).first()
                    
                    if not existing:
                        history = History(
                            user_id=user_id,
                            url=json.dumps(all_images),
                            type="电商商品套图",
                            thumbnail=all_images[0],
                            created_at=datetime.datetime.utcnow()
                        )
                        db.add(history)
            
            db.commit()
            print(f"[RQ-OTHER] 电商套图完成: task_id={task_id}")
            return {"task_id": task_id, "status": "completed"}
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"[RQ-OTHER] {task_name} 失败: task_id={task_id}, error={error_msg}")
        print(traceback.format_exc())
        
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = "failed"
                task.error_message = error_msg
                db.commit()
        except Exception as e2:
            print(f"[RQ-OTHER] 更新失败状态出错: {e2}")
        
        refund_credits(db, task_id, reason=f"{task_name}失败: {error_msg}")
        return {"task_id": task_id, "status": "failed", "error": error_msg}
    
    finally:
        db.close()

def _merge_angle_videos_sync(video_urls: list) -> str:
    """同步版视频合并（RQ Worker 中用）"""
    import subprocess
    import tempfile
    import os
    import requests
    from app.services.oss_service import oss_service
    import asyncio
    
    files_to_clean = []
    
    try:
        # 下载所有视频（同步版）
        video_files = []
        for url in video_urls:
            tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            resp = requests.get(url, timeout=60)
            tmp.write(resp.content)
            tmp.close()
            video_files.append(tmp.name)
            files_to_clean.append(tmp.name)
        
        # 创建 concat 文件列表
        list_file = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w")
        for vf in video_files:
            list_file.write(f"file '{vf}'\n")
        list_file.close()
        files_to_clean.append(list_file.name)
        
        # ffmpeg 合并
        output_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        output_file.close()
        files_to_clean.append(output_file.name)
        
        cmd = [
            "ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file.name,
            "-c", "copy", output_file.name, "-y"
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # 上传到 OSS
        with open(output_file.name, "rb") as f:
            video_bytes = f.read()
        
        # 同步上传（用 asyncio 执行异步方法）
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                oss_service.upload_file(video_bytes, "mp4", "multi_angle_videos")
            )
        finally:
            loop.close()
    
    finally:
        for f in files_to_clean:
            try:
                os.unlink(f)
            except:
                pass