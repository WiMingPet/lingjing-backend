from fastapi import APIRouter, Depends
from typing import List, Dict
from app.services.kling import KlingService
from app.utils.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/tts", tags=["语音合成"])


@router.get("/voices")
async def get_tts_voices(
    current_user: User = Depends(get_current_user)
) -> List[Dict]:
    """获取可灵 TTS 音色列表"""
    kling = KlingService()
    return kling.get_tts_voices()