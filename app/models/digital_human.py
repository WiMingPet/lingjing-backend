from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class DigitalHuman(Base):
    __tablename__ = "digital_humans"

    id = Column(Integer, primary_key=True, index=True)
    # 商家ID (创建者), 如果是默认数字人则为0
    merchant_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # 视频/图片URL
    source_video_url = Column(String(500), nullable=True)
    thumbnail_url = Column(String(500), nullable=True)

    # 元数据 - 改为 meta_data 避免与 SQLAlchemy 保留字冲突
    meta_data = Column(JSON, nullable=True)

    # 是否为默认数字人
    is_default = Column(Boolean, default=False)

    # 商家是否启用
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关系
    merchant = relationship("User", backref="digital_humans")

    def __repr__(self):
        return f"<DigitalHuman(id={self.id}, name={self.name}, is_default={self.is_default})>"