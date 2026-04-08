"""
认证路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.user import (
    SendVerificationCodeRequest,
    LoginRequest,
    TokenResponse,
    UserResponse,
    RegisterRequest
)
from app.schemas.task import APIResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/send_code", response_model=APIResponse)
def send_verification_code(
    request: SendVerificationCodeRequest,
    db: Session = Depends(get_db)
):
    """
    发送验证码
    模拟模式：固定返回 123456
    """
    result = AuthService.send_verification_code(request.phone)
    return APIResponse(
        code=200,
        message=result["message"],
        data=result
    )


@router.post("/login", response_model=APIResponse)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    验证码登录
    模拟模式：接受验证码 123456
    """
    try:
        result = AuthService.login(db, request.phone, request.code)
        return APIResponse(
            code=200,
            message="登录成功",
            data={
                "access_token": result["access_token"],
                "token_type": result["token_type"],
                "expires_in": result["expires_in"],
                "user": UserResponse.model_validate(result["user"])
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/register", response_model=APIResponse)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db)
):
    """
    用户注册 (密码注册)
    """
    try:
        user = AuthService.register(db, request.phone, request.password, request.username)
        return APIResponse(
            code=200,
            message="注册成功",
            data=UserResponse.model_validate(user)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/me", response_model=APIResponse)
def get_current_user(
    db: Session = Depends(get_db),
    current_user: UserResponse = Depends(lambda: None)  # 将在dependencies中实现
):
    """
    获取当前用户信息
    """
    # 将在dependencies中实现用户认证
    return APIResponse(
        code=200,
        message="获取成功",
        data=current_user
    )
