"""
多角度试穿路由
"""
import os
from fastapi import APIRouter, Depends, HTTPException, File, Form, UploadFile
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database import get_db
from app.schemas.task import APIResponse, TaskResponse
from app.services.multi_angle_service import MultiAngleService
from app.models.user import User
from app.utils.credits import check_and_deduct_credits
from app.utils.auth import get_current_user
from app.utils.file_utils import upload_file_helper
from app.data.prices import MULTI_ANGLE_COST
from app.rq_app import queue_other
from app.tasks.other_tasks import generate_multi_angle_task

router = APIRouter(prefix="/multi-angle", tags=["多角度试穿"])

# ========== 是否使用异步模式 ==========
USE_ASYNC = os.getenv("USE_ASYNC", "false").lower() == "true"
print(f"[MULTI_ANGLE] USE_ASYNC = {USE_ASYNC}")
# =====================================


@router.post("/generate", response_model=APIResponse)
async def generate_unified_character(
    images: List[UploadFile] = File(...),
    description: Optional[str] = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    多角度合成 - 上传2-4张不同角度照片，生成动态展示视频
    """
    from app.services.kling import kling_service

    # ========== 参数验证 ==========
    if len(images) < 2 or len(images) > 4:
        raise HTTPException(status_code=400, detail="请上传2-4张不同角度的照片")
    
    # ========== 上传图片 ==========
    image_urls = []
    for img in images:
        url, _ = await upload_file_helper(img, "multi_angle")
        image_urls.append(url)
        print(f"[DEBUG] 多角度图片已上传: {url}")
    
    print(f"[DEBUG] 共上传 {len(image_urls)} 张多角度照片")
    
    request_data = {
        "image_urls": image_urls,
        "description": description or ""
    }
    
    user = current_user
    user_id = current_user.id
    cost = MULTI_ANGLE_COST
    
    # ========== 判断模式 ==========
    if USE_ASYNC:
        # ========== 异步模式 ==========
        print(f"[MULTI_ANGLE] 使用异步模式")
        
        if queue_other is None:
            raise HTTPException(status_code=500, detail="异步队列未初始化，请检查Redis连接")
        
        # 先扣费
        check_and_deduct_credits(user, db, cost, "多角度试穿")
        
        # 创建任务
        from app.models.task import Task
        task = Task(
            user_id=user_id,
            task_type="multi_angle",
            status="pending",
            input_data=request_data,
            credits_cost=cost,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        # 提交队列
        job = queue_other.enqueue(generate_multi_angle_task, task.id, user_id, request_data)
        print(f"[MULTI_ANGLE] RQ 任务已提交: task_id={task.id}, job_id={job.id}")
        
        return APIResponse(
            code=200,
            message="多角度试穿任务已提交，预计2-3分钟完成",
            data={
                "task_id": task.id,
                "status": "pending",
                "async": True
            }
        )
    else:
        # ========== 同步模式（原有逻辑） ==========
        print(f"[MULTI_ANGLE] 使用同步模式")
        
        # 生成前检查余额
        if user.credits < cost:
            raise HTTPException(status_code=403, detail=f"多角度试穿需要{cost}灵境点，当前余额不足，请充值")
        
        # 2. 为每张图片调用可灵图生视频
        prompt = f"展示服装多角度细节，{description}，镜头缓慢旋转，专业灯光，4K高清" if description else "展示服装多角度细节，镜头缓慢旋转，专业灯光，4K高清"
        
        video_urls = []
        for i, img_url in enumerate(image_urls):
            print(f"[DEBUG] 生成第{i+1}个角度的视频...")
            task_id = kling_service.generate_video(
                image_url=img_url,
                prompt=f"{prompt}，第{i+1}个角度",
                duration=5,
                mode="std"
            )
            video_url = kling_service.wait_for_video_result(task_id, max_wait=600)
            if video_url.get("task_result", {}).get("video_url"):
                video_urls.append(video_url["task_result"]["video_url"])
        
        if not video_urls:
            raise HTTPException(status_code=500, detail="所有角度视频生成失败")
        
        # 3. ffmpeg 合并
        print(f"[DEBUG] 开始合并 {len(video_urls)} 个角度视频...")
        final_video_url = await _merge_angle_videos(video_urls)
        
        if not final_video_url:
            raise HTTPException(500, detail="多角度视频合成失败")
        
        # 生成成功后扣费
        check_and_deduct_credits(current_user, db, cost, "多角度试穿")
        
        # 提取封面图
        thumbnail_url = None
        try:
            from app.services.video_service import VideoService
            thumbnail_url = await VideoService.extract_thumbnail(final_video_url)
        except Exception as e:
            print(f"[DEBUG] 多角度封面提取失败: {e}")
        
        # 保存历史记录
        from app.models.history import History
        import datetime
        history = History(
            user_id=user_id,
            url=final_video_url,
            type="多角度试穿",
            thumbnail=thumbnail_url,
            created_at=datetime.datetime.utcnow()
        )
        db.add(history)
        db.commit()
        
        return APIResponse(
            code=200,
            message="多角度视频生成成功",
            data={"video_url": final_video_url, "thumbnail": thumbnail_url}
        )


# ========== 视频合并工具函数（同步模式用） ==========
async def _merge_angle_videos(video_urls: List[str]) -> str:
    """使用 ffmpeg 拼接多个视频片段"""
    import subprocess
    import tempfile
    import os
    import aiohttp
    from app.services.oss_service import oss_service
    
    files_to_clean = []
    
    try:
        video_files = []
        async with aiohttp.ClientSession() as session:
            for url in video_urls:
                tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
                async with session.get(url) as resp:
                    tmp.write(await resp.read())
                tmp.close()
                video_files.append(tmp.name)
                files_to_clean.append(tmp.name)
        
        list_file = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w")
        for vf in video_files:
            list_file.write(f"file '{vf}'\n")
        list_file.close()
        files_to_clean.append(list_file.name)
        
        output_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        output_file.close()
        files_to_clean.append(output_file.name)
        
        cmd = [
            "ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file.name,
            "-c", "copy", output_file.name, "-y"
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        with open(output_file.name, "rb") as f:
            return await oss_service.upload_file(f.read(), "mp4", "multi_angle_videos")
    
    finally:
        for f in files_to_clean:
            try:
                os.unlink(f)
            except:
                pass


@router.get("/task/{task_id}", response_model=APIResponse)
def get_multi_angle_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    """获取多角度合成任务状态"""
    task = MultiAngleService.get_task_result(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return APIResponse(
        code=200,
        message="获取成功",
        data=TaskResponse.model_validate(task)
    )