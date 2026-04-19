from pydantic import BaseModel
from typing import Optional, List

class ProductInfo(BaseModel):
    """商品结构化信息"""
    title: str  # 商品标题
    price: str  # 商品价格
    description: str  # 商品描述
    images: List[str]  # 商品图片URL列表
    platform: str  # 来源平台（taobao/jd/douyin等）

class CopywritingScript(BaseModel):
    """AI生成的带货脚本"""
    title: str  # 视频标题
    script: str  # 口播文案
    scenes: List[str]  # 分镜描述列表

class VideoTaskRequest(BaseModel):
    """视频生成请求"""
    url: str  # 商品链接
    digital_human_id: Optional[int] = None  # 数字人ID