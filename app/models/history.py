from sqlalchemy import Column, Integer, String, DateTime, Text
from app.database import Base
import datetime

class History(Base):
    __tablename__ = "histories"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)  # 不加 ForeignKey
    url = Column(Text, nullable=False)
    type = Column(Text, nullable=False)          # 改为 Text
    thumbnail = Column(Text, nullable=True)      # 改为 Text
    created_at = Column(DateTime, default=datetime.datetime.utcnow)