from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class DigitalHumanResponse(BaseModel):
    id: int
    merchant_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    source_video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    is_default: bool
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class DigitalHumanListResponse(BaseModel):
    total: int
    items: list[DigitalHumanResponse]


class DigitalHumanCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    source_video_id: str  # 上传的视频文件ID


class DigitalHumanUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
