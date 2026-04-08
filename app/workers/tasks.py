"""
异步任务处理
使用Redis + RQ任务队列
"""
from redis import Redis
from rq import Queue
from rq.job import Job
from typing import Optional
import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.database import SessionLocal
from app.models.task import Task
from app.models.digital_human import DigitalHuman
from app.services.image_service import ImageService
from app.services.video_service import VideoService
from app.services.size_service import SizeService
from app.services.tryon_service import TryOnService


def get_redis_queue() -> Queue:
    """获取Redis队列"""
    redis_conn = Redis.from_url(settings.REDIS_URL)
    return Queue(settings.RQ_QUEUE_NAME, connection=redis_conn)


# ========== 图片生成任务 ==========
def generate_image_task(task_id: int):
    """
    图片生成异步任务

    生产环境应调用可灵API进行真实图片生成
    """
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return

        task.status = "processing"
        db.commit()

        # 模拟处理过程
        for i in range(1, 101, 10):
            task.progress = i
            db.commit()

        # 调用Mock生成
        result = ImageService.mock_image_generation(task_id)

        # 更新任务结果
        task.status = "completed"
        task.progress = 100
        task.output_data = result
        db.commit()

    except Exception as e:
        task.status = "failed"
        task.error_message = str(e)
        db.commit()
    finally:
        db.close()


# ========== 视频生成任务 ==========
def generate_video_task(task_id: int):
    """
    视频生成异步任务

    根据task_type选择不同的生成逻辑
    生产环境应调用可灵API进行真实视频生成
    """
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return

        task.status = "processing"
        db.commit()

        # 获取输入数据
        input_data = task.input_data or {}
        task_type = task.task_type
        source_image_id = input_data.get("source_image_id")
        digital_human_id = task.digital_human_id

        # 如果未提供数字人，获取默认数字人
        if digital_human_id is None:
            default_dh = db.query(DigitalHuman).filter(
                DigitalHuman.is_default == True
            ).first()
            if default_dh:
                digital_human_id = default_dh.id
                task.digital_human_id = digital_human_id
                db.commit()

        # 根据视频类型选择不同的生成逻辑
        if task_type == "video_clothing_show":
            result = VideoService.generate_clothing_show_video(task_id, source_image_id)
        elif task_type == "video_tryon":
            result = VideoService.generate_tryon_video(task_id, source_image_id, digital_human_id)
        elif task_type == "video_product_show":
            result = VideoService.generate_product_show_video(task_id, source_image_id)
        else:
            result = VideoService.mock_video_generation(task_id, task_type, digital_human_id)

        # 模拟处理过程
        for i in range(1, 101, 10):
            task.progress = i
            db.commit()

        # 更新任务结果
        task.status = "completed"
        task.progress = 100
        task.output_data = result
        db.commit()

    except Exception as e:
        task.status = "failed"
        task.error_message = str(e)
        db.commit()
    finally:
        db.close()


# ========== 尺码推荐任务 ==========
def size_recommend_task(task_id: int, full_body_image_id: str, gender: str = "unisex", clothing_type: str = "general"):
    """
    尺码推荐异步任务

    使用MediaPipe提取特征，随机森林模型预测尺码
    """
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return

        task.status = "processing"
        db.commit()

        # 获取图片路径
        from app.config import settings
        image_path = os.path.join(settings.UPLOAD_DIR, "body_images", full_body_image_id)

        # 初始化服务
        size_service = SizeService()

        # 提取人体特征
        task.progress = 30
        db.commit()

        measurements = size_service.process_image(image_path)
        if measurements is None:
            raise Exception("无法识别图片中的人体")

        # 预测尺码
        task.progress = 60
        db.commit()

        result = size_service.predict_size(measurements, gender, clothing_type)

        # 更新任务结果
        task.progress = 100
        task.status = "completed"
        task.output_data = result
        db.commit()

    except Exception as e:
        task.status = "failed"
        task.error_message = str(e)
        db.commit()
    finally:
        db.close()


# ========== 多角度试穿任务 ==========
def multi_angle_tryon_task(task_id: int, source_images: list, digital_human_id: Optional[int] = None):
    """
    多角度试穿异步任务
    """
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return

        task.status = "processing"
        db.commit()

        # 如果未提供数字人，获取默认数字人
        if digital_human_id is None:
            default_dh = db.query(DigitalHuman).filter(
                DigitalHuman.is_default == True
            ).first()
            if default_dh:
                digital_human_id = default_dh.id

        # 模拟处理过程
        for i in range(1, 101, 10):
            task.progress = i
            db.commit()

        # Mock生成
        result = TryOnService.mock_multi_angle_tryon(task_id, source_images, digital_human_id)

        # 更新任务结果
        task.progress = 100
        task.status = "completed"
        task.output_data = result
        db.commit()

    except Exception as e:
        task.status = "failed"
        task.error_message = str(e)
        db.commit()
    finally:
        db.close()


# ========== 任务入队函数 ==========
def enqueue_image_task(task_id: int):
    """将图片生成任务加入队列"""
    queue = get_redis_queue()
    queue.enqueue(generate_image_task, task_id)


def enqueue_video_task(task_id: int):
    """将视频生成任务加入队列"""
    queue = get_redis_queue()
    queue.enqueue(generate_video_task, task_id)


def enqueue_size_task(task_id: int, full_body_image_id: str, gender: str = "unisex", clothing_type: str = "general"):
    """将尺码推荐任务加入队列"""
    queue = get_redis_queue()
    queue.enqueue(size_recommend_task, task_id, full_body_image_id, gender, clothing_type)


def enqueue_tryon_task(task_id: int, source_images: list, digital_human_id: Optional[int] = None):
    """将多角度试穿任务加入队列"""
    queue = get_redis_queue()
    queue.enqueue(multi_angle_tryon_task, task_id, source_images, digital_human_id)


if __name__ == "__main__":
    """
    启动Worker:
    python -m app.workers.tasks
    """
    print("Starting RQ Worker...")
    from rq import Worker
    queue = get_redis_queue()
    worker = Worker([queue], connection=queue.connection)
    worker.work()
