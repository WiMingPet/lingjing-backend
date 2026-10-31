"""
AI 短剧路由
"""
import os
import threading
from typing import List
from fastapi import APIRouter, Depends, Form, File, UploadFile, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user
from app.schemas.task import APIResponse
from app.utils.credits import check_and_deduct_credits
from app.rq_app import queue_other
from fastapi import Body
from app.tasks.other_tasks import generate_short_drama_task
from app.data.prices import SHORT_DRAMA_BASE_PRICE, SHORT_DRAMA_MODES

router = APIRouter(prefix="/short-drama", tags=["AI短剧"])

USE_ASYNC = os.getenv("USE_ASYNC", "false").lower() == "true"
print(f"[SHORT_DRAMA] USE_ASYNC = {USE_ASYNC}")


@router.post("/generate", response_model=APIResponse)
async def generate_short_drama(
    mode: str = Form(...),
    theme: str = Form(...),
    duration: int = Form(30),
    style: str = Form(None),
    language: str = Form("zh"), 
    reference_images: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if mode not in SHORT_DRAMA_MODES:
        raise HTTPException(400, f"无效模式: {mode}")

    if duration != 30:
        raise HTTPException(400, f"仅支持 30 秒，当前 {duration} 秒")
    cost = SHORT_DRAMA_BASE_PRICE.get(duration)
    if not cost:
        raise HTTPException(400, f"无效时长: {duration}")

    # 上传参考图
    reference_urls = []
    if reference_images and len(reference_images) > 0:
        if len(reference_images) > 10:
            raise HTTPException(400, "最多上传 10 张参考图")
        from app.utils.file_utils import upload_file_helper
        for img in reference_images:
            if img.filename:
                url, _ = await upload_file_helper(img, "short_drama/ref")
                reference_urls.append(url)

    # ★ 真人短剧：不强制上传（允许 AI 生成）
    # 之前是强制上传，现在取消

    request_data = {
        "mode": mode,
        "theme": theme,
        "duration": duration,
        "style": style,
        "reference_urls": reference_urls,
        "language": language, 
    }

    user = current_user
    user_id = current_user.id

    if USE_ASYNC:
        # 线上：RQ
        if queue_other is None:
            raise HTTPException(500, "队列未初始化")

        check_and_deduct_credits(user, db, cost, "AI短剧")

        from app.models.task import Task
        task = Task(
            user_id=user_id,
            task_type="short_drama",
            status="pending",
            input_data=request_data,
            credits_cost=cost,
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        queue_other.enqueue(generate_short_drama_task, task.id, user_id, request_data)

        return APIResponse(
            code=200,
            message=f"短剧任务已提交，需要 {cost} 点",
            data={"task_id": task.id, "status": "pending", "async": True, "cost": cost}
        )
    else:
        # 本地：线程
        if user.credits < cost:
            raise HTTPException(403, f"需要 {cost} 点")

        check_and_deduct_credits(user, db, cost, "AI短剧")

        from app.models.task import Task
        task = Task(
            user_id=user_id,
            task_type="short_drama",
            status="pending",
            input_data=request_data,
            credits_cost=cost,
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        def _worker():
            generate_short_drama_task(task.id, user_id, request_data)

        threading.Thread(target=_worker, daemon=True).start()

        return APIResponse(
            code=200,
            message=f"短剧任务已提交，需要 {cost} 点，预计 5-15 分钟完成",
            data={"task_id": task.id, "status": "pending", "async": True, "cost": cost}
        )


@router.get("/task/{task_id}", response_model=APIResponse)
def get_short_drama_task(task_id: int, db: Session = Depends(get_db)):
    from app.models.task import Task
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(404, "任务不存在")
    return APIResponse(
        code=200,
        message="获取成功",
        data={
            "task_id": task.id,
            "status": task.status,
            "output_data": task.output_data,
            "error_message": task.error_message,
        }
    )

@router.post("/parse-script", response_model=APIResponse)
async def parse_script(
    raw_text: str = Form(...),
    language: str = Form("zh"),
    reference_images: List[UploadFile] = File(default=[]),
    current_user: User = Depends(get_current_user),
):
    """解析用户剧本（不扣费），返回结构化 JSON + 时长 + 价格"""
    from app.services.script_generator import script_generator

    # 上传参考图
    reference_urls = []
    if reference_images and len(reference_images) > 0:
        if len(reference_images) > 10:
            raise HTTPException(400, "最多上传 10 张参考图")
        from app.utils.file_utils import upload_file_helper
        for img in reference_images:
            if img.filename:
                url, _ = await upload_file_helper(img, "short_drama/ref")
                reference_urls.append(url)

    try:
        parsed = await script_generator.parse_user_script(raw_text, language, reference_urls)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 固定 30 秒
    total_duration = 30
    parsed["total_duration"] = 30

    # 算价格
    from app.data.prices import SHORT_DRAMA_BASE_PRICE
    cost = SHORT_DRAMA_BASE_PRICE.get(30, 350)

    return APIResponse(
        code=200,
        message="解析成功",
        data={
            "parsed": parsed,
            "total_duration": total_duration,
            "cost": cost,
            "reference_urls": reference_urls,
        }
    )

@router.post("/generate-from-script", response_model=APIResponse)
async def generate_from_script(
    parsed_script: dict = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """用户脚本模式：扣费 + 生成（不调 AI 生成剧本）"""
    from app.services.script_generator import script_generator
    from app.data.prices import SHORT_DRAMA_BASE_PRICE
    from app.utils.credits import check_and_deduct_credits
    from app.models.task import Task
    from app.rq_app import queue_other
    from app.tasks.other_tasks import generate_short_drama_task
    import os

    total_duration = parsed_script.get("total_duration", 30)
    if total_duration > 60:
        raise HTTPException(status_code=400, detail="剧本超过 60 秒，无法生成")

    cost = SHORT_DRAMA_BASE_PRICE.get(total_duration, 0)
    if not cost:
        raise HTTPException(status_code=400, detail="无法计算价格")

    # 扣费
    check_and_deduct_credits(
        current_user, db, cost,
        f"AI短剧（用户剧本，{total_duration}秒）"
    )

    # 把用户脚本转成 prompts
    scenes = script_generator.convert_user_script_to_prompts(parsed_script)

    # 构建 request_data（和 AI 生成模式一样，但带 scenes）
    request_data = {
        "mode": parsed_script.get("mode", "real"),
        "theme": parsed_script.get("title", "用户剧本"),
        "duration": total_duration,
        "language": parsed_script.get("language", "zh"),
        "user_script": parsed_script,      # 标记：用户脚本模式
        "scenes": scenes,                   # 已转换的 prompts
        "characters": parsed_script.get("characters", []),
        "reference_urls": parsed_script.get("reference_urls", []),
    }

    # 创建任务
    task = Task(
        user_id=current_user.id,
        task_type="short_drama",
        status="pending",
        input_data=request_data,
        credits_cost=cost,
        progress=0
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # 提交队列
    use_async = os.getenv("USE_ASYNC", "false").lower() == "true"
    if use_async and queue_other:
        queue_other.enqueue(generate_short_drama_task, task.id, current_user.id, request_data)
        return APIResponse(
            code=200,
            message=f"任务已提交，需要 {cost} 点",
            data={"task_id": task.id, "async": True, "cost": cost}
        )
    else:
        # 本地同步
        import threading
        threading.Thread(
            target=generate_short_drama_task,
            args=(task.id, current_user.id, request_data),
            daemon=True
        ).start()
        return APIResponse(
            code=200,
            message=f"任务已提交，需要 {cost} 点",
            data={"task_id": task.id, "async": True, "cost": cost}
        )