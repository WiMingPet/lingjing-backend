import os
import random
import string
from datetime import datetime
from alipay import AliPay

class PaymentService:

    def __init__(self):
        app_private_key_string = os.environ.get("ALIPAY_PRIVATE_KEY", "")
        alipay_public_key_string = os.environ.get("ALIPAY_PUBLIC_KEY", "")
        
        # 将字符串中的 \n 还原为真实换行符
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

    def query_order(self, out_trade_no: str) -> dict:
        result = self.alipay.api_alipay_trade_query(out_trade_no=out_trade_no)
        return result