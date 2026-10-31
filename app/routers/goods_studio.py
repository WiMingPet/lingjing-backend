"""
商品成片路由
"""
import os
import threading
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.user import User
from app.models.task import Task
from app.utils.credits import check_and_deduct_credits
from app.utils.auth import get_current_user
from app.rq_app import queue_other
from app.tasks.goods_studio_tasks import generate_goods_studio_task

router = APIRouter(prefix="/goods-studio", tags=["商品成片"])

USE_ASYNC = os.getenv("USE_ASYNC", "false").lower() == "true"
print(f"[GOODS_STUDIO] USE_ASYNC = {USE_ASYNC}")

# 只有 15 秒，固定扣 300 点
GOODS_STUDIO_COST = 300


@router.post("/generate")
async def generate_goods_studio(
    images: List[UploadFile] = File(...),
    title: str = Form(...),
    description: str = Form(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if len(images) == 0:
        raise HTTPException(status_code=400, detail="请上传商品图")

    if len(images) > 5:
        raise HTTPException(status_code=400, detail="商品图最多 5 张")

    # ★ 1. 最前置检查：如果线上且队列挂了，直接拦截，不建任务、不扣费、不传图
    if USE_ASYNC and queue_other is None:
        raise HTTPException(500, "系统繁忙（队列未初始化），请稍后再试")

    # 上传图片到 OSS
    from app.services.oss_service import oss_service
    image_urls = []
    for img in images:
        content = await img.read()
        ext = img.filename.split(".")[-1] if "." in img.filename else "jpg"
        url = await oss_service.upload_file(content, ext, "goods_studio")
        image_urls.append(url)

    # ★ 2. 建任务
    task = Task(
        user_id=user.id,
        task_type="goods_studio",
        status="pending",
        input_data={
            "image_urls": image_urls,
            "title": title,
            "description": description,
            "duration": 15,
        },
        credits_cost=GOODS_STUDIO_COST,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # ★ 3. 扣费
    check_and_deduct_credits(user, db, GOODS_STUDIO_COST, "商品成片")

    # ★ 4. 分发
    if USE_ASYNC:
        queue_other.enqueue(generate_goods_studio_task, task.id, user.id, task.input_data)
    else:
        threading.Thread(
            target=generate_goods_studio_task,
            args=(task.id, user.id, task.input_data),
            daemon=True
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