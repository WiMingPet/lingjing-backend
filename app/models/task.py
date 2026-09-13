from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    task_type = Column(String(50), nullable=False, index=True)
    status = Column(String(20), default="pending", index=True)

    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    progress = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

    digital_human_id = Column(Integer, ForeignKey("digital_humans.id"), nullable=True)

    # ========== 新增：退款相关 ==========
    credits_cost = Column(Integer, default=0)          # 扣费金额
    refunded = Column(Boolean, default=False)          # 是否已退款
    refunded_at = Column(DateTime(timezone=True), nullable=True)  # 退款时间
    # ===================================

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", backref="tasks")
    digital_human = relationship("DigitalHuman", backref="tasks")

    def __repr__(self):
        return f"<Task(id={self.id}, task_type={self.task_type}, status={self.status})>"