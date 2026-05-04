from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from app.database import Base
import datetime

class History(Base):
    __tablename__ = "histories"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    url = Column(Text, nullable=False)           # 改为 Text
    type = Column(Text, nullable=False)          # 改为 Text
    thumbnail = Column(Text, nullable=True)      # 改为 Text
    created_at = Column(DateTime, default=datetime.datetime.utcnow)