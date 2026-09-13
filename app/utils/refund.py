"""
统一退款工具 - 防止重复退款
"""
import datetime
from sqlalchemy.orm import Session
from sqlalchemy import update
from app.models.task import Task
from app.models.user import User


def refund_credits(db: Session, task_id: int, reason: str = "") -> bool:
    """
    安全退款：原子操作 + 防重复
    
    逻辑：
    1. 原子更新 task：只有 refunded=False 时才更新为 True
    2. 如果更新成功，说明是首次退款，执行退款
    3. 如果更新失败，说明已退款，跳过
    """
    try:
        # ========== 第一步：原子标记任务为"已退款" ==========
        result = db.execute(
            update(Task)
            .where(Task.id == task_id, Task.refunded == False)
            .values(refunded=True, refunded_at=datetime.datetime.utcnow())
        )
        
        if result.rowcount == 0:
            # 任务不存在，或已退款
            db.rollback()
            print(f"[REFUND] ⚠️ 任务不存在或已退款，跳过: task_id={task_id}")
            return False
        
        # ========== 第二步：查询任务，获取退款金额和用户 ==========
        task = db.query(Task).filter(Task.id == task_id).first()
        
        if not task or not task.credits_cost or task.credits_cost <= 0:
            db.commit()
            print(f"[REFUND] ⚠️ 无需退款: task_id={task_id}, credits_cost={task.credits_cost if task else 'N/A'}")
            return False
        
        # ========== 第三步：原子退款到用户账户 ==========
        result = db.execute(
            update(User)
            .where(User.id == task.user_id)
            .values(credits=User.credits + task.credits_cost)
        )
        
        if result.rowcount == 0:
            db.rollback()
            print(f"[REFUND] ❌ 用户不存在: user_id={task.user_id}")
            return False
        
        # ========== 第四步：提交事务 ==========
        db.commit()
        
        # 查询退款后的余额（用于日志）
        user = db.query(User).filter(User.id == task.user_id).first()
        print(f"[REFUND] ✅ 退款成功: user_id={task.user_id}, "
              f"credits={task.credits_cost}, task_id={task_id}, "
              f"当前余额={user.credits if user else 'N/A'}, 原因={reason}")
        return True
    
    except Exception as e:
        db.rollback()
        print(f"[REFUND] ❌ 退款异常: task_id={task_id}, error={e}")
        return False