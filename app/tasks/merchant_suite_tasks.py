"""
套图生成 RQ 任务 v3（支持部分成功按比例退款）
"""
import asyncio
import datetime
import json
from app.database import SessionLocal
from app.models.task import Task
from app.models.history import History
from app.utils.refund import refund_credits


def generate_suite_task(task_id: int, user_id: int, request_data: dict):
    """后台执行套图生成"""
    print(f"[RQ-SUITE] 开始: task_id={task_id}")

    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return {"error": "任务不存在"}

        task.status = "processing"
        db.commit()

        suite_type = request_data.get("suite_type")
        cloth_url = request_data.get("cloth_url")
        analysis = request_data.get("analysis", {})
        count = request_data.get("count", 1)
        unit_cost = request_data.get("unit_cost", 10)   # ★ 从 request_data 拿

        from app.services.suite_generator import suite_generator

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if suite_type == "white_bg":
                images = loop.run_until_complete(suite_generator.generate_white_bg(cloth_url))
            elif suite_type == "scene":
                images = loop.run_until_complete(suite_generator.generate_scene_images(cloth_url, analysis, count))
            elif suite_type == "premium_aplus":
                images = loop.run_until_complete(suite_generator.generate_premium_aplus(cloth_url, analysis, count))
            elif suite_type == "standard_aplus":
                images = loop.run_until_complete(suite_generator.generate_standard_aplus(cloth_url, analysis, count))
            elif suite_type == "phone_aplus":
                images = loop.run_until_complete(suite_generator.generate_phone_aplus(cloth_url, analysis, count))
            else:
                raise Exception(f"无效的套图类型: {suite_type}")
        finally:
            loop.close()

        # ★ 全部失败：抛错，全额退款
        if not images:
            raise Exception("套图生成失败，未获取到图片")

        actual_count = len(images)

        # ★ 部分成功：按比例退款
        refund_amount = 0
        if actual_count < count:
            refund_count = count - actual_count
            refund_amount = unit_cost * refund_count
            print(f"[RQ-SUITE] 部分成功: {actual_count}/{count}，退款 {refund_amount} 点")

            try:
                tmp_task = Task(
                    user_id=user_id,
                    task_type="merchant_suite_partial_refund",
                    status="failed",
                    input_data=request_data,
                    credits_cost=refund_amount,
                )
                db.add(tmp_task)
                db.commit()
                db.refresh(tmp_task)
                refund_credits(db, tmp_task.id, reason=f"部分成功: {actual_count}/{count}")
                print(f"[RQ-SUITE] 已退款 {refund_amount} 点")
            except Exception as refund_err:
                print(f"[RQ-SUITE] 退款失败: {refund_err}")

        task.status = "completed"
        task.progress = 100
        task.completed_at = datetime.datetime.utcnow()
        db.commit()

        history = History(
            user_id=user_id,
            url=json.dumps(images),
            type="电商商品套图",
            thumbnail=images[0]["watermarked"] if images else None,
            created_at=datetime.datetime.utcnow()
        )
        db.add(history)
        db.commit()
        db.refresh(history)

        task.output_data = {
            "images": images,
            "analysis": analysis,
            "history_id": history.id,
            "refund_amount": refund_amount,
            "actual_count": actual_count,
        }
        db.commit()

        print(f"[RQ-SUITE] 完成: task_id={task_id}, 生成 {actual_count}/{count} 张，退款 {refund_amount} 点")
        return {"task_id": task_id, "status": "completed", "images": images}

    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"[RQ-SUITE] 失败: task_id={task_id}, error={error_msg}")
        print(traceback.format_exc())

        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = "failed"
                task.error_message = error_msg
                db.commit()
        except Exception as e2:
            print(f"[RQ-SUITE] 更新失败状态出错: {e2}")

        # ★ 全额退款
        refund_credits(db, task_id, reason=f"套图生成失败: {error_msg}")
        return {"task_id": task_id, "status": "failed", "error": error_msg}

    finally:
        db.close()