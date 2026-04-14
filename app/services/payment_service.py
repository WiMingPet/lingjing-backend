import os
import random
import string
from datetime import datetime
from alipay import AliPay

class PaymentService:
    
    def __init__(self):
        # 从环境变量获取私钥
        app_private_key_string = os.environ.get("ALIPAY_PRIVATE_KEY", "")
        alipay_public_key_string = os.environ.get("ALIPAY_PUBLIC_KEY", "")
        
        # 处理可能存在的转义字符
        if '\\n' in app_private_key_string:
            app_private_key_string = app_private_key_string.replace('\\n', '\n')
        if '\\n' in alipay_public_key_string:
            alipay_public_key_string = alipay_public_key_string.replace('\\n', '\n')
        
        # 去掉可能的首尾引号
        if app_private_key_string.startswith('"') and app_private_key_string.endswith('"'):
            app_private_key_string = app_private_key_string[1:-1]
        if alipay_public_key_string.startswith('"') and alipay_public_key_string.endswith('"'):
            alipay_public_key_string = alipay_public_key_string[1:-1]
        
        self.alipay = AliPay(
            appid=os.environ.get("ALIPAY_APP_ID"),
            app_notify_url=os.environ.get("ALIPAY_NOTIFY_URL"),
            app_private_key_string=app_private_key_string,
            alipay_public_key_string=alipay_public_key_string,
            sign_type="RSA2",
            debug=False
        )
    
    def generate_order_no(self) -> str:
        """生成商户订单号"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        random_str = ''.join(random.choices(string.digits, k=6))
        return f"{timestamp}{random_str}"
    
    def create_page_pay_order(self, out_trade_no: str, total_amount: float, 
                               subject: str, body: str, return_url: str) -> str:
        """
        创建电脑网站支付订单
        返回支付页面 URL，前端跳转到该 URL 即可
        """
        order_string = self.alipay.api_alipay_trade_page_pay(
            out_trade_no=out_trade_no,
            total_amount=total_amount,
            subject=subject,
            body=body,
            return_url=return_url,
            notify_url=os.environ.get("ALIPAY_NOTIFY_URL")
        )
        
        # 构建完整的支付 URL
        pay_url = f"https://openapi.alipay.com/gateway.do?{order_string}"
        return pay_url
    
    def query_order(self, out_trade_no: str) -> dict:
        """查询订单状态"""
        result = self.alipay.api_alipay_trade_query(out_trade_no=out_trade_no)
        return result