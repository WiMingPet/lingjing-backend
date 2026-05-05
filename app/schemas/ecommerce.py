from pydantic import BaseModel
from typing import Optional, List

class ProductInfo(BaseModel):
    """商品结构化信息"""
    title: str
    price: str
    description: str
    images: List[str]
    platform: str
    video_url: Optional[str] = None  # 新增

class CopywritingScript(BaseModel):
    """AI生成的带货脚本"""
    title: str
    script: str
    scenes: List[str]

class VideoTaskRequest(BaseModel):
    url: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    digital_image_url: Optional[str] = None
    digital_human_id: Optional[int] = None

# ========== 新增模型 ==========

class GenerateVideoRequest(BaseModel):
    """生成视频请求参数"""
    url: str


class GenerateVideoResponse(BaseModel):
    """生成视频响应参数"""
    success: bool
    video_url: Optional[str] = None
    product_info: Optional[dict] = None
    script: Optional[str] = None
    error: Optional[str] = None
    need_image: bool = False


class ParseUrlResponse(BaseModel):
    """解析链接响应参数"""
    code: int
    message: str
    data: Optional[dict] = None