from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """获取密码哈希"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建JWT访问令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """解码JWT令牌"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


# 验证码模拟存储 (生产环境应使用Redis)
VERIFICATION_CODES = {}


def generate_verification_code(phone: str) -> str:
    """
    生成验证码
    模拟模式：固定返回 123456
    """
    # 生产环境应该生成随机6位数字
    code = "123456"
    VERIFICATION_CODES[phone] = {
        "code": code,
        "expires": datetime.utcnow() + timedelta(minutes=5)
    }
    return code


def verify_verification_code(phone: str, code: str) -> bool:
    """
    验证验证码
    模拟模式：接受 123456
    """
    if phone not in VERIFICATION_CODES:
        return code == "123456"  # 模拟模式也接受123456

    stored = VERIFICATION_CODES[phone]
    if datetime.utcnow() > stored["expires"]:
        del VERIFICATION_CODES[phone]
        return False

    # 模拟模式接受任意正确格式的验证码
    return stored["code"] == code or code == "123456"
