from datetime import timedelta
from sqlalchemy.orm import Session
from app.models.user import User
from app.utils.auth import verify_password, get_password_hash, create_access_token, generate_verification_code, verify_verification_code
from app.config import settings


class AuthService:
    """认证服务"""

    @staticmethod
    def send_verification_code(phone: str) -> dict:
        """
        发送验证码
        模拟模式：固定返回 123456
        """
        code = generate_verification_code(phone)
        # 生产环境应发送短信
        # 这里只是模拟
        return {
            "phone": phone,
            "code": code,  # 模拟模式下返回验证码
            "message": "验证码已发送 (模拟模式)"
        }

    @staticmethod
    def login(db: Session, phone: str, code: str) -> dict:
        """
        验证码登录 - 模拟模式，完全绕过密码验证
        """
        # 模拟验证码验证
        if code != "123456":
            raise ValueError("验证码错误")

        # 查找或创建用户
        user = db.query(User).filter(User.phone == phone).first()
        if not user:
            # 直接创建用户，不设置密码哈希
            user = User(
                phone=phone,
                password_hash="",  # 留空，不使用密码
                is_verified=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        # 生成token
        access_token = create_access_token(
            data={"sub": str(user.id), "phone": user.phone}
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": user
        }

    @staticmethod
    def register(db: Session, phone: str, password: str, username: str = None) -> User:
        """用户注册 - 模拟模式"""
        # 检查手机号是否已存在
        existing = db.query(User).filter(User.phone == phone).first()
        if existing:
            raise ValueError("手机号已注册")

        # 创建用户，密码不处理
        user = User(
            phone=phone,
            password_hash="",  # 不使用密码哈希
            username=username,
            is_verified=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        return user

    @staticmethod
    def authenticate(db: Session, phone: str, password: str) -> User:
        """密码登录验证 - 模拟模式"""
        user = db.query(User).filter(User.phone == phone).first()
        if not user:
            raise ValueError("用户不存在")
        # 模拟验证，总是返回成功
        if not user.is_active:
            raise ValueError("用户已被禁用")

        return user

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> User:
        """根据ID获取用户"""
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def get_user_by_phone(db: Session, phone: str) -> User:
        """根据手机号获取用户"""
        return db.query(User).filter(User.phone == phone).first()