"""
商家数字人定制服务
"""
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.digital_human import DigitalHuman


class DigitalHumanService:
    """数字人服务"""

    @staticmethod
    async def create_digital_human(
        db: Session,
        merchant_id: int,
        name: str,
        description: Optional[str] = None,
        source_video_id: Optional[str] = None
    ) -> DigitalHuman:
        """
        创建数字人

        Args:
            db: 数据库会话
            merchant_id: 商家ID
            name: 数字人名称
            description: 描述
            source_video_id: 源视频ID

        Returns:
            DigitalHuman: 创建的数字人
        """
        # 生成Mock的视频URL和缩略图URL
        # 生产环境应上传到OSS
        source_video_url = f"https://example.com/digital_human/{source_video_id}.mp4"
        thumbnail_url = f"https://example.com/digital_human/thumb_{source_video_id}.jpg"

        digital_human = DigitalHuman(
            merchant_id=merchant_id,
            name=name,
            description=description,
            source_video_url=source_video_url,
            thumbnail_url=thumbnail_url,
            is_default=False,
            is_active=True
        )
        db.add(digital_human)
        db.commit()
        db.refresh(digital_human)

        return digital_human

    @staticmethod
    def get_digital_human(db: Session, digital_human_id: int) -> Optional[DigitalHuman]:
        """获取数字人"""
        return db.query(DigitalHuman).filter(DigitalHuman.id == digital_human_id).first()

    @staticmethod
    def list_digital_humans(
        db: Session,
        merchant_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20
    ) -> List[DigitalHuman]:
        """
        列出数字人

        Args:
            db: 数据库会话
            merchant_id: 商家ID (可选)
            skip: 跳过数量
            limit: 限制数量

        Returns:
            List[DigitalHuman]: 数字人列表
        """
        query = db.query(DigitalHuman).filter(DigitalHuman.is_active == True)

        if merchant_id is not None:
            query = query.filter(
                (DigitalHuman.merchant_id == merchant_id) | (DigitalHuman.is_default == True)
            )

        return query.offset(skip).limit(limit).all()

    @staticmethod
    def count_digital_humans(db: Session, merchant_id: Optional[int] = None) -> int:
        """统计数字人数量"""
        query = db.query(func.count(DigitalHuman.id)).filter(DigitalHuman.is_active == True)
        if merchant_id is not None:
            query = query.filter(
                (DigitalHuman.merchant_id == merchant_id) | (DigitalHuman.is_default == True)
            )
        return query.scalar()

    @staticmethod
    def update_digital_human(
        db: Session,
        digital_human_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Optional[DigitalHuman]:
        """更新数字人"""
        digital_human = db.query(DigitalHuman).filter(DigitalHuman.id == digital_human_id).first()
        if not digital_human:
            return None

        if name is not None:
            digital_human.name = name
        if description is not None:
            digital_human.description = description
        if is_active is not None:
            digital_human.is_active = is_active

        db.commit()
        db.refresh(digital_human)
        return digital_human

    @staticmethod
    def delete_digital_human(db: Session, digital_human_id: int) -> bool:
        """删除数字人 (软删除)"""
        digital_human = db.query(DigitalHuman).filter(DigitalHuman.id == digital_human_id).first()
        if not digital_human:
            return False

        # 软删除
        digital_human.is_active = False
        db.commit()
        return True

    @staticmethod
    def get_default_digital_human(db: Session) -> Optional[DigitalHuman]:
        """获取默认数字人"""
        return db.query(DigitalHuman).filter(DigitalHuman.is_default == True).first()

    @staticmethod
    def create_default_digital_human(db: Session) -> DigitalHuman:
        """创建默认数字人"""
        default_dh = DigitalHuman(
            merchant_id=None,
            name="默认数字人",
            description="系统默认数字人，用于用户未选择数字人时的试穿视频生成",
            source_video_url="https://example.com/default_digital_human.mp4",
            thumbnail_url="https://example.com/default_digital_human.jpg",
            is_default=True,
            is_active=True
        )
        db.add(default_dh)
        db.commit()
        db.refresh(default_dh)
        return default_dh
