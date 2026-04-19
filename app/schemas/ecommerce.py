from pydantic import BaseModel
from typing import Optional, List

class ProductInfo(BaseModel):
    """商品结构化信息"""
    title: str
    price: str
    description: str
    images: List[str]
    platform: str

class CopywritingScript(BaseModel):
    """AI生成的带货脚本"""
    title: str
    script: str
    scenes: List[str]

class VideoTaskRequest(BaseModel):
    """视频生成请求"""
    title: Optional[str] = None
    price: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    digital_human_id: Optional[int] = None