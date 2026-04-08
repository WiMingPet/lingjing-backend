from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 任务类型: image_gen, video_clothing_show, video_tryon, video_product_show, size_recommend, multi_angle_tryon
    task_type = Column(String(50), nullable=False, index=True)

    # 任务状态: pending, processing, completed, failed
    status = Column(String(20), default="pending", index=True)

    # 输入数据 (JSON格式存储)
    input_data = Column(JSON, nullable=True)

    # 输出数据 (JSON格式存储)
    output_data = Column(JSON, nullable=True)

    # 进度百分比
    progress = Column(Integer, default=0)

    # 错误信息
    error_message = Column(Text, nullable=True)

    # 关联的数字人ID (可选)
    digital_human_id = Column(Integer, ForeignKey("digital_humans.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # 关系
    user = relationship("User", backref="tasks")
    digital_human = relationship("DigitalHuman", backref="tasks")

    def __repr__(self):
        return f"<Task(id={self.id}, task_type={self.task_type}, status={self.status})>"
