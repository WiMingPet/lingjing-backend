from fastapi import HTTPException
from app.models.user import User
from sqlalchemy.orm import Session

def check_and_deduct_credits(
    user: User, 
    db: Session, 
    cost: int, 
    action_name: str = "操作"
) -> bool:
    """检查余额并扣除灵境点"""
    if user.credits < cost:
        raise HTTPException(
            status_code=403, 
            detail=f"{action_name}需要{cost}灵境点，当前余额不足，请充值"
        )
    
    user.credits -= cost
    db.add(user)
    db.commit()
    return True