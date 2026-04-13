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
        host = os.environ.get('REDIS_HOST', 'localhost')
        port = int(os.environ.get('REDIS_PORT', 6379))
        
        logger.info(f"Redis连接: host={host}, port={port}")
        
        return redis.Redis(
            host=host,
            port=port,
            decode_responses=True
        )

    @staticmethod
    def _get_sms_client():
        """获取阿里云短信客户端"""
        access_key_id = os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_ID')
        access_key_secret = os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_SECRET')
        
        logger.info(f"阿里云配置: AccessKeyId={access_key_id[:6]}***")
        
        config = open_api_models.Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret
        )
        config.endpoint = 'dysmsapi.aliyuncs.com'
        return DysmsapiClient(config)

    @staticmethod
    def send_verification_code(phone: str) -> dict:
        """
        发送短信验证码（真实调用阿里云短信）
        """
        logger.info(f"开始发送验证码: phone={phone}")
        
        # 1. 生成6位随机验证码
        code = str(random.randint(100000, 999999))
        logger.info(f"生成验证码: {code}")
        
        # 2. 存入Redis，5分钟过期
        try:
            r = AuthService._get_redis_client()
            r.setex(f"sms_code:{phone}", 300, code)
            logger.info(f"验证码已存入Redis: phone={phone}")
        except Exception as e:
            logger.error(f"Redis存储失败: {str(e)}")
            return {
                "phone": phone,
                "code": code,
                "message": f"Redis存储失败: {str(e)}，验证码: {code}"
            }
        
        # 3. 获取短信配置
        sign_name = os.environ.get('SMS_SIGN_NAME')
        template_code = os.environ.get('SMS_TEMPLATE_CODE')
        
        logger.info(f"短信配置: sign_name={sign_name}, template_code={template_code}")
        
        if not sign_name or not template_code:
            error_msg = f"短信配置缺失: sign_name={sign_name}, template_code={template_code}"
            logger.error(error_msg)
            return {
                "phone": phone,
                "code": code,
                "message": f"短信配置缺失: {error_msg}，验证码: {code}"
            }
        
        # 4. 发送短信
        try:
            client = AuthService._get_sms_client()
            send_request = dysmsapi_models.SendSmsRequest(
                phone_numbers=phone,
                sign_name=sign_name,
                template_code=template_code,
                template_param=f'{{"code":"{code}"}}'
            )
            
            logger.info(f"发送短信请求: phone={phone}, code={code}")
            response = client.send_sms(send_request)
            
            logger.info(f"短信响应: code={response.body.code}, message={response.body.message}, request_id={response.body.request_id}")
            
            if response.body.code != 'OK':
                error_msg = f"短信发送失败: {response.body.code} - {response.body.message}"
                logger.error(error_msg)
                return {
                    "phone": phone,
                    "code": code,
                    "message": f"{error_msg}，验证码: {code}"
                }
            
            logger.info(f"短信发送成功: phone={phone}")
            return {
                "phone": phone,
                "code": "",
                "message": "验证码已发送"
            }
            
        except Exception as e:
            logger.error(f"短信SDK异常: {str(e)}", exc_info=True)
            return {
                "phone": phone,
                "code": code,
                "message": f"短信服务异常: {str(e)}，验证码: {code}"
            }

    @staticmethod
    def verify_code(phone: str, code: str) -> bool:
        """验证验证码"""
        try:
            r = AuthService._get_redis_client()
            stored_code = r.get(f"sms_code:{phone}")
            if not stored_code:
                logger.warning(f"验证码不存在或已过期: phone={phone}")
                return False
            result = stored_code == code
            logger.info(f"验证码验证: phone={phone}, result={result}")
            return result
        except Exception as e:
            logger.error(f"验证码验证异常: {str(e)}")
            return False

    @staticmethod
    def delete_code(phone: str):
        """删除验证码"""
        try:
            r = AuthService._get_redis_client()
            r.delete(f"sms_code:{phone}")
            logger.info(f"验证码已删除: phone={phone}")
        except Exception as e:
            logger.error(f"删除验证码异常: {str(e)}")