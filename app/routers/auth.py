"""
认证路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.database import get_db
from app.schemas.user import (
    SendVerificationCodeRequest,
    LoginRequest,
    TokenResponse,
    UserResponse,
    RegisterRequest,
    VerifyCodeRequest
)
from app.schemas.task import APIResponse
from app.services.auth_service import AuthService
from app.models.user import User
from passlib.context import CryptContext
import jwt
from app.config import settings

router = APIRouter(prefix="/auth", tags=["认证"])

# 使用 pbkdf2_sha256，无密码长度限制
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# JWT配置
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7天


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/send_code", response_model=APIResponse)
def send_verification_code(
    request: SendVerificationCodeRequest,
    db: Session = Depends(get_db)
):
    """发送验证码"""
    result = AuthService.send_verification_code(request.phone)
    return APIResponse(
        code=200,
        message=result["message"],
        data=result
    )


@router.post("/verify_code", response_model=APIResponse)
def verify_code(
    request: VerifyCodeRequest,
    db: Session = Depends(get_db)
):
    """
    验证短信验证码
    """
    phone = request.phone
    code = request.code
    
    import redis
    import os
    r = redis.Redis(
        host=os.environ.get('REDIS_HOST', 'localhost'),
        port=int(os.environ.get('REDIS_PORT', 6379)),
        decode_responses=True
    )
    
    stored_code = r.get(f"sms_code:{phone}")
    
    if not stored_code:
        raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")
    
    if stored_code != code:
        raise HTTPException(status_code=400, detail="验证码错误")
    
    # ❌ 注释掉这行，不要删除验证码
    # r.delete(f"sms_code:{phone}")
    
    return APIResponse(code=200, message="验证成功")


@router.post("/login", response_model=APIResponse)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    登录（支持密码登录和验证码登录）
    """
    user = db.query(User).filter(User.phone == request.phone).first()
    if not user:
        raise HTTPException(status_code=400, detail="手机号未注册")
    
    # 密码登录
    if request.password:
        if not verify_password(request.password, user.password_hash):
            raise HTTPException(status_code=400, detail="密码错误")
    # 验证码登录 - 验证 Redis 中的真实验证码
    elif request.code:
        import redis
        import os
        r = redis.Redis(
            host=os.environ.get('REDIS_HOST', 'localhost'),
            port=int(os.environ.get('REDIS_PORT', 6379)),
            decode_responses=True
        )
        stored_code = r.get(f"sms_code:{request.phone}")
        if not stored_code:
            raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")
        if stored_code != request.code:
            raise HTTPException(status_code=400, detail="验证码错误")
        # 验证成功，删除验证码
        r.delete(f"sms_code:{request.phone}")
    else:
        raise HTTPException(status_code=400, detail="请提供密码或验证码")
    
    token = create_access_token(data={"sub": str(user.id), "phone": user.phone})
    
    return APIResponse(
        code=200,
        message="登录成功",
        data={
            "access_token": token,
            "token_type": "bearer",
            "user_id": user.id,
            "phone": user.phone,
            "credits": user.credits if hasattr(user, 'credits') else 0
        }
    )


@router.post("/register", response_model=APIResponse)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db)
):
    """
    短信验证码注册
    """
    # 1. 检查手机号是否已存在
    existing_user = db.query(User).filter(User.phone == request.phone).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="手机号已注册")
    
    # 2. 验证短信验证码（从Redis获取）
    import redis
    import os
    r = redis.Redis(
        host=os.environ.get('REDIS_HOST', 'localhost'),
        port=int(os.environ.get('REDIS_PORT', 6379)),
        decode_responses=True
    )
    stored_code = r.get(f"sms_code:{request.phone}")
    
    if not stored_code:
        raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")
    
    if stored_code != request.code:
        raise HTTPException(status_code=400, detail="验证码错误")
    
    # 3. 验证通过，删除验证码
    r.delete(f"sms_code:{request.phone}")
    
    # 4. 创建用户
    hashed_pwd = hash_password(request.password)
    user = User(
        phone=request.phone,
        password_hash=hashed_pwd,
        username=request.username or request.phone,
        is_active=True,
        is_verified=True,
        credits=20
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # 5. 生成token
    token = create_access_token(data={"sub": str(user.id), "phone": user.phone})
    
    return APIResponse(
        code=200,
        message="注册成功",
        data={
            "access_token": token,
            "token_type": "bearer",
            "user_id": user.id,
            "phone": user.phone,
            "credits": user.credits
        }
    )


@router.get("/me", response_model=APIResponse)
def get_current_user(
    db: Session = Depends(get_db),
    current_user: User = Depends(lambda: None)
):
    """获取当前用户信息"""
    return APIResponse(
        code=200,
        message="获取成功",
        data=None
    )