import os
import random
import string
from datetime import datetime
from alipay import AliPay

class PaymentService:

    def __init__(self):
        # 优先从配置文件读取（Zeabur Config Files）
        private_key_path = "/app/alipay_private_key.pem"
        public_key_path = "/app/alipay_public_key.pem"
        
        if os.path.exists(private_key_path):
            with open(private_key_path, 'r') as f:
                app_private_key_string = f.read()
        else:
            app_private_key_string = os.environ.get("ALIPAY_PRIVATE_KEY", "")
        
        if os.path.exists(public_key_path):
            with open(public_key_path, 'r') as f:
                alipay_public_key_string = f.read()
        else:
            alipay_public_key_string = os.environ.get("ALIPAY_PUBLIC_KEY", "")
        
        # 处理转义字符
        app_private_key_string = app_private_key_string.replace('\\n', '\n')
        alipay_public_key_string = alipay_public_key_string.replace('\\n', '\n')

        self.alipay = AliPay(
            appid=os.environ.get("ALIPAY_APP_ID"),
            app_notify_url=os.environ.get("ALIPAY_NOTIFY_URL"),
            app_private_key_string=app_private_key_string,
            alipay_public_key_string=alipay_public_key_string,
            sign_type="RSA2",
            debug=False
        )

    def generate_order_no(self) -> str:
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        random_str = ''.join(random.choices(string.digits, k=6))
        return f"{timestamp}{random_str}"

    def create_wap_pay_order(self, out_trade_no: str, total_amount: float,
                               subject: str, body: str, return_url: str) -> str:
        order_string = self.alipay.api_alipay_trade_wap_pay(
            out_trade_no=out_trade_no,
            total_amount=total_amount,
            subject=subject,
            body=body,
            return_url=return_url,
            notify_url=os.environ.get("ALIPAY_NOTIFY_URL")
        )
        pay_url = f"https://openapi.alipay.com/gateway.do?{order_string}"
        return pay_url

    def create_qr_code_order(self, out_trade_no: str, total_amount: float, 
                               subject: str, body: str) -> str:
        """创建当面付二维码订单，返回二维码内容"""
        order = self.alipay.api_alipay_trade_precreate(
            out_trade_no=out_trade_no,
            total_amount=total_amount,
            subject=subject,
            body=body,
            timeout_express="30m"
        )
        
        if order.get("code") == "10000":
            return order.get("qr_code")
        else:
            raise Exception(f"创建订单失败: {order.get('msg')}")

    def query_order(self, out_trade_no: str) -> dict:
        result = self.alipay.api_alipay_trade_query(out_trade_no=out_trade_no)
        return result