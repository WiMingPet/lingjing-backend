from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    module = Column(String(50), index=True)       # image / video / tryon / ai_drama / digital_custom / merchant
    title = Column(String(200))
    thumbnail = Column(String(500))               # 封面图
    preview_video = Column(String(500))           # 大卡自动播放视频（其他卡可空）
    result_url = Column(String(500))              # 结果视频/图片
    template_prompt = Column(Text)                # 提示词
    template_params = Column(Text)                # JSON 参数
    section = Column(String(50), index=True)      # ai_video / ai_fun
    position = Column(Integer, default=0)         # 分区内顺序
    is_case = Column(Boolean, default=False)      # 首页展示
    is_template = Column(Boolean, default=False)  # 模块内模板
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())