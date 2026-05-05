"""
多角度试穿路由
"""
from fastapi import APIRouter, Depends, HTTPException, File, Form
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database import get_db
from app.schemas.task import APIResponse, TaskResponse
from app.services.multi_angle_service import MultiAngleService
from app.models.user import User  # ✅ 新增：导入用户模型
from app.utils.credits import check_and_deduct_credits  # ✅ 新增：导入扣除工具
from app.utils.auth import get_current_user  # ✅ 新增：导入获取用户工具
from app.utils.file_utils import upload_file_helper

router = APIRouter(prefix="/multi-angle", tags=["多角度试穿"])


@router.post("/generate", response_model=APIResponse)
async def generate_unified_character(
    images: List[UploadFile] = File(...),  # 接收2-4张照片
    description: Optional[str] = Form(""),  # 描述文字
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    多角度合成 - 上传2-4张不同角度照片，生成动态展示视频
    
    - **images**: 2-4张不同角度的照片
    - **description**: 描述文字（可选）
    """
    from app.services.kling import kling_service
    
    # 验证图片数量
    if len(images) < 2 or len(images) > 4:
        raise HTTPException(status_code=400, detail="请上传2-4张不同角度的照片")
    
    # ✅ 检查并扣除 10 点灵境点
    check_and_deduct_credits(current_user, db, 10, "多角度试穿")
    
    # 1. 上传所有图片到 OSS
    image_urls = []
    for img in images:
        url, _ = await upload_file_helper(img, "multi_angle")
        image_urls.append(url)
        print(f"[DEBUG] 多角度图片已上传: {url}")
    
    print(f"[DEBUG] 共上传 {len(image_urls)} 张多角度照片")
    
    # 2. 为每张图片调用可灵图生视频
    prompt = f"展示服装多角度细节，{description}，镜头缓慢旋转，专业灯光，4K高清" if description else "展示服装多角度细节，镜头缓慢旋转，专业灯光，4K高清"
    
    video_urls = []
    for i, img_url in enumerate(image_urls):
        print(f"[DEBUG] 生成第{i+1}个角度的视频...")
        task_id = kling_service.generate_video(
            image_url=img_url,
            prompt=f"{prompt}，第{i+1}个角度",
            duration=3,
            mode="std"
        )
        video_url = kling_service.wait_for_video_result(task_id, max_wait=300)
        if video_url.get("task_result", {}).get("video_url"):
            video_urls.append(video_url["task_result"]["video_url"])
        print(f"[DEBUG] 第{i+1}个角度视频: {video_urls[-1] if video_urls else 'failed'}")
    
    if not video_urls:
        raise HTTPException(status_code=500, detail="所有角度视频生成失败")
    
    # 3. 用 ffmpeg 拼接所有视频片段
    print(f"[DEBUG] 开始合并 {len(video_urls)} 个角度视频...")
    final_video_url = await _merge_angle_videos(video_urls)
    print(f"[DEBUG] 多角度视频合成完成: {final_video_url}")
    
    return APIResponse(
        code=200,
        message="多角度视频生成成功",
        data={"video_url": final_video_url}
    )


# ========== 视频合并工具函数 ==========
async def _merge_angle_videos(video_urls: List[str]) -> str:
    """使用 ffmpeg 拼接多个视频片段"""
    import subprocess
    import tempfile
    import os
    import aiohttp
    from app.services.oss_service import oss_service
    
    files_to_clean = []
    
    try:
        # 下载所有视频
        video_files = []
        async with aiohttp.ClientSession() as session:
            for url in video_urls:
                tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
                async with session.get(url) as resp:
                    tmp.write(await resp.read())
                tmp.close()
                video_files.append(tmp.name)
                files_to_clean.append(tmp.name)
        
        # 创建 ffmpeg concat 文件列表
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