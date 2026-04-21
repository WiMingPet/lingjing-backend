"""
电商视频数据模型
文件路径: app/schemas/ecommerce.py
"""

from pydantic import BaseModel
from typing import Optional


class GenerateVideoRequest(BaseModel):
    """请求参数"""
    url: str  # 抖音商品链接


class GenerateVideoResponse(BaseModel):
    """响应参数"""
    success: bool
    video_url: Optional[str] = None
    product_info: Optional[dict] = None
    script: Optional[str] = None
    error: Optional[str] = None
    need_image: bool = False  # 是否需要用户上传图片