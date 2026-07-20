from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user
from app.models.history import History
from pydantic import BaseModel
from typing import Optional
from app.services.video_service import VideoService

router = APIRouter(prefix="/history", tags=["历史记录"])

class SaveHistoryRequest(BaseModel):
    url: str
    type: str
    thumbnail: Optional[str] = None

@router.post("/save")
async def save_history(
    request: SaveHistoryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    print(f"[DEBUG] 收到保存请求: type={request.type}, url={request.url[:50] if request.url else 'None'}...")
    
    # ========== ✅ 去重检查 ==========
    if request.url:
        existing = db.query(History).filter(
            History.user_id == current_user.id,
            History.url == request.url,
            History.type == request.type
        ).first()
        if existing:
            print(f"[DEBUG] 记录已存在，跳过保存: {request.url[:50]}...")
            return {"code": 200, "message": "记录已存在"}
    # 自动生成封面（如果是视频且未提供封面）
    thumbnail_url = request.thumbnail
    if not thumbnail_url and request.type in ["数字人分身", "视频生成", "AI带货视频", "虚拟试穿"]:
        try:
            thumbnail_url = await VideoService.extract_thumbnail(request.url)
        except Exception as e:
            print(f"[DEBUG] 封面生成失败（不影响保存）: {e}")

    history = History(
        user_id=current_user.id,
        url=request.url,
        type=request.type,
        thumbnail=thumbnail_url
    )
    db.add(history)
    db.commit()
    return {"code": 200, "message": "保存成功"}

@router.delete("/{history_id}")
def delete_history(
    history_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    item = db.query(History).filter(
        History.id == history_id,
        History.user_id == current_user.id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(item)
    db.commit()
    return {"code": 200, "message": "已删除"}

@router.get("/list")
async def get_history(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    items = db.query(History).filter(
        History.user_id == current_user.id
    ).order_by(History.created_at.desc()).limit(limit).all()
    
    return {
        "code": 200,
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