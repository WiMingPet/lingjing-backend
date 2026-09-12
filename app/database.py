from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=10,           # 连接池大小
    max_overflow=20,        # 超出池大小的最大连接数
    pool_pre_ping=True,     # 连接前检查
    pool_recycle=3600,      # 连接回收时间（1小时）
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库"""
    from app.models import user, task, digital_human, order
    Base.metadata.create_all(bind=engine)