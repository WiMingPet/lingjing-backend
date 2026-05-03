from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models.user import User
from app.models.history import History
from app.utils.auth import get_current_user

router = APIRouter(prefix="/history", tags=["历史记录"])


class SaveHistoryRequest(BaseModel):
    url: str
    type: str
    thumbnail: Optional[str] = None


class HistoryItem(BaseModel):
    id: int
    url: str
    type: str
    thumbnail: Optional[str] = None
    timestamp: datetime


@router.post("/save")
async def save_history(
    request: SaveHistoryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """保存历史记录"""
    history = History(
        user_id=current_user.id,
        url=request.url,
        type=request.type,
        thumbnail=request.thumbnail
    )
    db.add(history)
    db.commit()
    
    return {
        "code": 200,
        "message": "保存成功",
        "data": {"id": history.id}
    }


@router.get("/list")
async def get_history(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取用户的历史记录列表"""
    items = db.query(History).filter(
        History.user_id == current_user.id
    ).order_by(History.created_at.desc()).limit(limit).all()
    
    return {
        "code": 200,
        "message": "获取成功",
        "data": [
            {
                "id": h.id,
                "url": h.url,
                "type": h.type,
                "thumbnail": h.thumbnail,
                "timestamp": h.created_at
            }
            for h in items
        ]
    }


@router.delete("/{history_id}")
async def delete_history(
    history_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除单条历史记录"""
    history = db.query(History).filter(
        History.id == history_id,
        History.user_id == current_user.id
    ).first()
    
    if not history:
        raise HTTPException(status_code=404, detail="记录不存在")
    
    db.delete(history)
    db.commit()
    
    return {"code": 200, "message": "删除成功"}