from fastapi import HTTPException
from app.models.user import User
from sqlalchemy.orm import Session
from sqlalchemy import update


def check_and_deduct_credits(
    user: User, 
    db: Session, 
    cost: int, 
    action_name: str = "操作"
) -> bool:
    """原子扣费：数据库层面保证扣费成功或失败"""
    result = db.execute(
        update(User)
        .where(User.id == user.id, User.credits >= cost)
        .values(credits=User.credits - cost)
    )
    
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(
            status_code=403,
            detail=f"{action_name}需要{cost}灵境点，当前余额不足，请充值"
        )
    
    db.commit()
    db.refresh(user)
    
    print(f"[DEDUCT] 扣费成功: user_id={user.id}, cost={cost}, 余额={user.credits}, 原因={action_name}")
    return True