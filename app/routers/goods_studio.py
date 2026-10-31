"""
商品成片路由
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.user import User
from app.models.task import Task
from app.utils.credits import check_and_deduct_credits
from app.utils.auth import get_current_user
import os
USE_ASYNC = os.getenv("USE_ASYNC", "false").lower() == "true"
print(f"[GOODS_STUDIO] USE_ASYNC = {USE_ASYNC}")

router = APIRouter()

GOODS_STUDIO_PRICES = {
    15: 300,
    30: 500,
    60: 800,
}


@router.post("/generate")
async def generate_goods_studio(
    images: List[UploadFile] = File(...),
    title: str = Form(...),
    description: str = Form(""),
    duration: int = Form(15),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if duration not in GOODS_STUDIO_PRICES:
        raise HTTPException(status_code=400, detail="时长仅支持 15/30/60 秒")

    if len(images) == 0:
        raise HTTPException(status_code=400, detail="请上传商品图")

    if len(images) > 5:
        raise HTTPException(status_code=400, detail="商品图最多 5 张")

    # 先上传图片到 OSS
    from app.services.oss_service import oss_service
    image_urls = []
    for img in images:
        content = await img.read()
        ext = img.filename.split(".")[-1] if "." in img.filename else "jpg"
        url = await oss_service.upload_file(content, ext, "goods_studio")
        image_urls.append(url)

    cost = GOODS_STUDIO_PRICES[duration]

    task = Task(
        user_id=user.id,
        task_type="goods_studio",
        status="pending",
        input_data={
            "image_urls": image_urls,
            "title": title,
            "description": description,
            "resolution": "1080p",
            "aspect_ratio": "16:9",
            "duration": duration,
        },
        credits_cost=cost,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    check_and_deduct_credits(user, db, cost, "商品成片")

    from app.tasks.goods_studio_tasks import generate_goods_studio_task

    if USE_ASYNC:
        from rq import Queue
        from app.redis_client import redis_conn
        q = Queue("other", connection=redis_conn)
        q.enqueue(generate_goods_studio_task, task.id, user.id, task.input_data)
    else:
        import threading
        threading.Thread(
            target=generate_goods_studio_task,
            args=(task.id, user.id, task.input_data),
        ).start()

    return {"task_id": task.id, "status": "pending"}


@router.get("/task/{task_id}")
async def get_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return {
        "task_id": task.id,
        "status": task.status,
        "output_data": task.output_data,
        "error_message": task.error_message,
    }