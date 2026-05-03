from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from app.database import Base
import datetime

class History(Base):
    __tablename__ = "histories"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    url = Column(String(500), nullable=False)
    type = Column(String(50), nullable=False)  # 视频生成, 图片生成, 数字人分身, 虚拟试穿等
    thumbnail = Column(String(500), nullable=True)  # 封面图URL（可选）
    created_at = Column(DateTime, default=datetime.datetime.utcnow)