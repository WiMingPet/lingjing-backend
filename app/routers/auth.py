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
    VerifyCodeRequest,
    ResetPasswordRequest  # 添加这一行
)
from app.schemas.task import APIResponse
from app.services.auth_service import AuthService
from app.models.user import User
from passlib.context import CryptContext
import jwt
from app.config import settings
from app.utils.auth import get_current_user as get_current_user_from_token

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
    验证码登录：如果用户不存在，自动创建账号
    """
    import redis
    import os
    import logging
    logger = logging.getLogger(__name__)
    
    # 密码登录
    if request.password:
        user = db.query(User).filter(User.phone == request.phone).first()
        if not user:
            raise HTTPException(status_code=400, detail="手机号未注册")
        if not verify_password(request.password, user.password_hash):
            raise HTTPException(status_code=400, detail="密码错误")
        logger.info(f"密码登录成功: {request.phone}")
    
    # 验证码登录（支持免注册）
    elif request.code:
        # 1. 验证验证码
        r = redis.Redis(
            host=os.environ.get('REDIS_HOST', 'localhost'),
            port=int(os.environ.get('REDIS_PORT', 6379)),
            decode_responses=True
        )
        stored_code = r.get(f"sms_code:{request.phone}")
        logger.info(f"验证码登录 - 手机号: {request.phone}, 输入: {request.code}, Redis: {stored_code}")
        
        if not stored_code:
            raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")
        if stored_code != request.code:
            raise HTTPException(status_code=400, detail="验证码错误")
        
        # 验证成功，删除验证码（一次性使用）
        r.delete(f"sms_code:{request.phone}")
        
        # 2. 查找或创建用户
        user = db.query(User).filter(User.phone == request.phone).first()
        if not user:
            # 自动创建用户（免注册）
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
            # 生成一个随机密码（用户不会使用密码登录）
            random_password = os.urandom(16).hex()
            hashed_pwd = pwd_context.hash(random_password)
            
            user = User(
                phone=request.phone,
                password_hash=hashed_pwd,
                username=request.phone,  # 默认用户名用手机号
                is_active=True,
                is_verified=True,
                credits=10  # 新用户送10灵境点
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"验证码登录自动创建用户: {request.phone}")
        
        logger.info(f"验证码登录成功: {request.phone}")
    
    else:
        raise HTTPException(status_code=400, detail="请提供密码或验证码")
    
    # 生成token
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
    注册（如果用户已存在，返回错误）
    """
    # 检查手机号是否已存在
    existing_user = db.query(User).filter(User.phone == request.phone).first()
    if existing_user:
        # 如果用户已存在，可以选择直接登录
        # 这里为了安全，仍然返回错误，让用户使用登录接口
        raise HTTPException(status_code=400, detail="手机号已注册，请直接登录")
    
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
    current_user: User = Depends(get_current_user_from_token)
):
    """获取当前用户信息"""
    if not current_user:
        return APIResponse(
            code=401,
            message="未登录",
            data=None
        )
    
    return APIResponse(
        code=200,
        message="获取成功",
        data={
            "id": current_user.id,
            "phone": current_user.phone,
            "username": current_user.username,
            "credits": current_user.credits,
            "is_active": current_user.is_active,
            "is_verified": current_user.is_verified,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None
        }
    )


@router.post("/reset_password", response_model=APIResponse)
def reset_password(
    request_data: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    找回密码 - 通过验证码重置密码
    """
    import redis
    import os
    from passlib.context import CryptContext
    
    pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
    
    phone = request_data.phone
    code = request_data.code
    new_password = request_data.new_password
    
    # 验证验证码
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
    
    # 查找用户
    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        raise HTTPException(status_code=400, detail="用户不存在")
    
    # 重置密码
    user.password_hash = pwd_context.hash(new_password)
    db.commit()
    
    # 删除验证码
    r.delete(f"sms_code:{phone}")
    
    return APIResponse(
        code=200,
        message="密码重置成功"
    )