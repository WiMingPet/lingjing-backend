from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from datetime import datetime


# 统一响应格式
class APIResponse(BaseModel):
    code: int = 200
    message: str = "Success"
    data: Optional[Any] = None


# ========== 图片生成 ==========
class ImageGenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1000)
    negative_prompt: Optional[str] = None
    width: int = 512
    height: int = 512
    num_images: int = Field(default=1, ge=1, le=4)
    reference_image_id: Optional[str] = None  # 参考图文件ID


# ========== 视频生成 ==========
class VideoGenerationRequest(BaseModel):
    # 视频类型: video_clothing_show, video_tryon, video_product_show
    task_type: str = Field(..., pattern=r"^(video_clothing_show|video_tryon|video_product_show)$")
    source_image_id: str  # 上传的图片ID
    digital_human_id: Optional[int] = None  # 可选，使用商家的数字人
    # video_clothing_show: 衣服展示视频
    # video_tryon: 试穿视频
    # video_product_show: 家电展示视频


# ========== 尺码推荐 ==========
class SizeRecommendRequest(BaseModel):
    full_body_image_id: str  # 全身照文件ID
    gender: str = Field(default="unisex", pattern=r"^(male|female|unisex)$")
    clothing_type: str = Field(default="general", pattern=r"^(shirt|pants|dress|coat|general)$")


# ========== 多角度试穿 ==========
class MultiAngleTryOnRequest(BaseModel):
    source_images: List[str] = Field(..., min_items=2, max_items=5)  # 多张图片ID
    digital_human_id: Optional[int] = None


# ========== 数字人创建 ==========
class DigitalHumanCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    source_video_id: str  # 上传的视频文件ID


# ========== 任务状态 ==========
class TaskResponse(BaseModel):
    id: int
    task_type: str
    status: str
    progress: int
    input_data: Optional[Dict] = None
    output_data: Optional[Dict] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ========== 尺码推荐结果 ==========
class SizeRecommendResponse(BaseModel):
    height: float  # 身高(cm)
    weight: float  # 体重(kg)
    bust: float  # 胸围(cm)
    waist: float  # 腰围(cm)
    hip: float  # 臀围(cm)
    recommended_size: str  # 推荐尺码
    confidence: float  # 置信度


# ========== 文件上传响应 ==========
class FileUploadResponse(BaseModel):
    file_id: str
    file_name: str
    file_type: str
    file_url: str
    size: int
