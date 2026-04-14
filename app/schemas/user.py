from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# 发送验证码请求
class SendVerificationCodeRequest(BaseModel):
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$")


# 验证码登录请求
class LoginRequest(BaseModel):
    phone: str
    password: Optional[str] = None
    code: Optional[str] = None


# Token响应
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# 用户信息
class UserResponse(BaseModel):
    id: int
    phone: str
    username: Optional[str] = None
    is_active: bool
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


# 注册请求
class RegisterRequest(BaseModel):
    phone: str
    password: str
    code: str
    username: Optional[str] = None


# 验证验证码请求（新增）
class VerifyCodeRequest(BaseModel):
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$")
    code: str = Field(..., min_length=6, max_length=6)