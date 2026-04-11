"""
认证相关的数据模型
"""
from typing import Optional
from pydantic import BaseModel


class RegisterRequest(BaseModel):
    phone: str
    password: str
    username: Optional[str] = None


class LoginRequest(BaseModel):
    phone: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    phone: str
    credits: int = 0