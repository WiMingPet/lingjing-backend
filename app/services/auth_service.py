import os
import random
import logging
import redis
from datetime import datetime, timedelta
from alibabacloud_dysmsapi20170525.client import Client as DysmsapiClient
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_dysmsapi20170525 import models as dysmsapi_models

logger = logging.getLogger(__name__)


class AuthService:
    """认证服务"""

    @staticmethod
    def _get_redis_client():
        """获取Redis连接"""
        import os
        import redis
    
        # 优先使用 REDIS_URL
        redis_url = os.environ.get('REDIS_URL')
        if redis_url:
            return redis.Redis.from_url(redis_url, decode_responses=True)
    
        # 备用：使用分离的配置
        host = os.environ.get('REDIS_HOST', 'localhost')
        port = int(os.environ.get('REDIS_PORT', 6379))
        password = os.environ.get('REDIS_PASSWORD', None)
    
        return redis.Redis(
            host=host,
            port=port,
            password=password,
            decode_responses=True
        )

    @staticmethod
    def _get_sms_client():
        """获取阿里云短信客户端"""
        config = open_api_models.Config(
            access_key_id=os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_ID'),
            access_key_secret=os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_SECRET')
        )
        config.endpoint = 'dysmsapi.aliyuncs.com'
        return DysmsapiClient(config)

    @staticmethod
    def send_verification_code(phone: str) -> dict:
        """
        发送短信验证码（真实调用阿里云短信）
        """
        # 1. 生成6位随机验证码
        code = str(random.randint(100000, 999999))
        
        # 2. 存入Redis，5分钟过期
        r = AuthService._get_redis_client()
        r.setex(f"sms_code:{phone}", 300, code)
        
        # 3. 获取短信配置
        sign_name = os.environ.get('SMS_SIGN_NAME')
        template_code = os.environ.get('SMS_TEMPLATE_CODE')
        
        # 4. 发送短信（生产环境）
        try:
            client = AuthService._get_sms_client()
            send_request = dysmsapi_models.SendSmsRequest(
                phone_numbers=phone,
                sign_name=sign_name,
                template_code=template_code,
                template_param=f'{{"code":"{code}"}}'
            )
            response = client.send_sms(send_request)
            
            if response.body.code != 'OK':
                logger.error(f"短信发送失败: {response.body.message}")
                # 降级：返回验证码用于调试
                return {
                    "phone": phone,
                    "code": code,
                    "message": f"短信发送失败: {response.body.message}，验证码: {code}"
                }
            
            logger.info(f"短信发送成功: {phone}")
            return {
                "phone": phone,
                "code": "",  # 生产环境不返回验证码
                "message": "验证码已发送"
            }
            
        except Exception as e:
            logger.error(f"短信SDK异常: {str(e)}")
            return {
                "phone": phone,
                "code": code,
                "message": f"短信服务异常，请稍后重试，验证码: {code}"
            }

    @staticmethod
    def verify_code(phone: str, code: str) -> bool:
        """验证验证码"""
        r = AuthService._get_redis_client()
        stored_code = r.get(f"sms_code:{phone}")
        if not stored_code:
            return False
        return stored_code == code

    @staticmethod
    def delete_code(phone: str):
        """删除验证码"""
        r = AuthService._get_redis_client()
        r.delete(f"sms_code:{phone}")