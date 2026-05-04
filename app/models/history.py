from sqlalchemy import Column, Integer, DateTime, Text
from app.database import Base
import datetime

class History(Base):
    __tablename__ = "histories"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)  # 不加外键约束，避免依赖问题
    url = Column(Text, nullable=False)         # Text 无长度限制
    type = Column(Text, nullable=False)        # Text
    thumbnail = Column(Text, nullable=True)    # Text
    created_at = Column(DateTime, default=datetime.datetime.utcnow)