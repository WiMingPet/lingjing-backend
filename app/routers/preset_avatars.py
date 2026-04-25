from fastapi import APIRouter
from typing import List
from app.data.preset_avatars import PRESET_AVATARS  # 引用上一步的数据

router = APIRouter(prefix="/digital-human", tags=["数字人"])


@router.get("/preset-avatars")
async def get_preset_avatars() -> List[dict]:
    """获取所有预设形象列表"""
    return PRESET_AVATARS