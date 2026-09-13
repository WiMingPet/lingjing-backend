"""
商家数字人定制路由
"""
import os
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
import json
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.task import APIResponse
from app.schemas.digital_human import (
    DigitalHumanResponse,
    DigitalHumanListResponse,
    DigitalHumanCreateRequest,
    DigitalHumanUpdateRequest
)
from app.services.digital_human_service import DigitalHumanService
from app.utils.file_utils import upload_file_helper
from app.utils.credits import check_and_deduct_credits
from app.data.prices import DIGITAL_HUMAN_COST
from app.rq_app import queue_other
from app.tasks.other_tasks import generate_digital_human_task

router = APIRouter(prefix="/digital-human", tags=["数字人定制"])

# ========== 是否使用异步模式 ==========
USE_ASYNC = os.getenv("USE_ASYNC", "false").lower() == "true"
print(f"[DIGITAL_HUMAN] USE_ASYNC = {USE_ASYNC}")
# =====================================


# ========== 创建数字人（保持不变） ==========
@router.post("/", response_model=APIResponse)
async def create_digital_human(
    name: str = Form(...),
    description: str = Form(None),
    source_video: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建数字人"""
    # 检查并扣除 60 灵境点
    if current_user.credits < 60:
        raise HTTPException(status_code=403, detail="定制数字人需要60灵境点，当前余额不足")
    check_and_deduct_credits(current_user, db, 60, "定制数字人")
    
    # 上传视频
    file_url, file_id = await upload_file_helper(source_video, "digital_human_videos")
    source_video_id = file_id

    # 创建数字人
    digital_human = await DigitalHumanService.create_digital_human(
        db=db,
        merchant_id=current_user.id,
        name=name,
        description=description,
        source_video_id=source_video_id
    )

    return APIResponse(
        code=200,
        message="数字人创建成功",
        data=DigitalHumanResponse.model_validate(digital_human)
    )


# ========== 列表、详情、更新、删除（保持不变） ==========
# ... 你现有的代码 ...


# ========== 数字人分身生成视频（改造） ==========
@router.post("/generate", response_model=APIResponse)
async def generate_digital_human(
    image_url: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    audio: Optional[UploadFile] = File(None),
    prompt: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """数字人分身 - 照片+文字/音频生成说话视频"""
    import uuid
    from app.services.oss_service import oss_service
    from app.services.kling import kling_service
    from app.services.tts_service import tts_service
    
    # 强制清空无意义的默认值
    if prompt == "string":
        prompt = None
    if name == "string":
        name = None
    
    # 1. 处理图片
    if image_url:
        final_image_url = image_url
        print(f"[DEBUG] 使用形象库图片 URL: {final_image_url}")
    elif image:
        final_image_url, image_id = await upload_file_helper(image, "digital_human/images")
        print(f"[DEBUG] 手动上传图片已保存: {final_image_url}")
    else:
        raise HTTPException(status_code=400, detail="请提供图片 URL 或上传图片文件")

    # 图片安全审核
    from app.services.image_service import ImageService
    if not await ImageService.check_image_safety(final_image_url):
        raise HTTPException(status_code=400, detail="图片未通过安全审核，请更换图片")

    # 2. 获取音频
    audio_url = None
    if text:
        audio_data = tts_service.text_to_speech(text, voice_type=502001)
        audio_url = await oss_service.upload_file(audio_data, "mp3", "digital_human/audio")
        print(f"[DEBUG] TTS 生成音频成功: {text[:50]}...")
    elif audio:
        audio_content = await audio.read()
        audio_ext = audio.filename.split('.')[-1] if audio.filename else 'mp3'
        audio_url = await oss_service.upload_file(audio_content, audio_ext, "digital_human/audio")
        print(f"[DEBUG] 使用用户上传音频")
    else:
        raise HTTPException(status_code=400, detail="请提供文字内容或音频文件")
    
    # ========== 构建请求数据 ==========
    request_data = {
        "image_url": final_image_url,
        "audio_url": audio_url,
        "text": text,
        "voice": None,  # 你现有的代码用 tts_service 直接生成，不需要 voice
        "prompt": prompt,
        "name": name,
    }
    
    user = current_user
    user_id = current_user.id
    cost = DIGITAL_HUMAN_COST
    
    # ========== 判断模式 ==========
    if USE_ASYNC:
        # ========== 异步模式 ==========
        print(f"[DIGITAL_HUMAN] 使用异步模式")
        
        if queue_other is None:
            raise HTTPException(status_code=500, detail="异步队列未初始化")
        
        # 先扣费
        check_and_deduct_credits(user, db, cost, "数字人分身")
        
        # 创建任务
        from app.models.task import Task
        task = Task(
            user_id=user_id,
            task_type="digital_human",
            status="pending",
            input_data=request_data,
            credits_cost=cost,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        # 提交队列
        job = queue_other.enqueue(generate_digital_human_task, task.id, user_id, request_data)
        print(f"[DIGITAL_HUMAN] RQ 任务已提交: task_id={task.id}, job_id={job.id}")
        
        return APIResponse(
            code=200,
            message="数字人视频生成任务已提交，预计2-5分钟完成",
            data={
                "task_id": task.id,
                "status": "pending",
                "async": True
            }
        )
    else:
        # ========== 同步模式（原有逻辑） ==========
        print(f"[DIGITAL_HUMAN] 使用同步模式")
        
        # 余额检查
        if user.credits < cost:
            raise HTTPException(status_code=403, detail=f"数字人分身需要{cost}灵境点，当前余额不足")
        
        # 生成前不扣费，成功后扣费（原子扣费）
        
        # 3. 调用可灵虚拟形象 API
        api_task_id = await kling_service.generate_digital_human(
            image_url=final_image_url,
            audio_url=audio_url,
            prompt=prompt,
            name=name
        )
        print(f"[DEBUG] 数字人任务ID: {api_task_id}")
        
        # 4. 轮询等待结果
        result = kling_service.wait_for_digital_human_result(api_task_id)
        video_url = result.get("task_result", {}).get("video_url", "")
        print(f"[DEBUG] 数字人视频URL: {video_url}")
        
        if not video_url:
            raise HTTPException(500, detail="数字人视频生成失败")
        
        # 生成成功后扣费
        check_and_deduct_credits(user, db, cost, "数字人分身")

        # ========== 自动保存历史记录 ==========
        from app.models.history import History
        from app.services.video_service import VideoService
        
        existing = db.query(History).filter(
            History.user_id == user_id,
            History.url == video_url,
            History.type == "数字人分身"
        ).first()
        
        if not existing:
            thumbnail = None
            try:
                thumbnail = await VideoService.extract_thumbnail(video_url)
            except Exception as e:
                print(f"[DEBUG] 封面生成失败: {e}")
            
            history = History(
                user_id=user_id,
                url=video_url,
                type="数字人分身",
                thumbnail=thumbnail
            )
            db.add(history)
            db.commit()

        return APIResponse(
            code=200,
            message="数字人视频生成成功",
            data={"video_url": video_url, "task_id": api_task_id}
        )


@router.get("/preset-avatars")
async def get_preset_avatars() -> List[dict]:
    """获取所有预设形象列表"""
    from app.data.preset_avatars import PRESET_AVATARS
    return PRESET_AVATARS