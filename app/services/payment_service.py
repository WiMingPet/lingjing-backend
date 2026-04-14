import os
import random
import string
from alipay import AliPay

class PaymentService:
    
    def __init__(self):
        self.alipay = AliPay(
            appid=os.environ.get("ALIPAY_APP_ID"),
            app_notify_url=os.environ.get("ALIPAY_NOTIFY_URL"),
            app_private_key_string=os.environ.get("ALIPAY_PRIVATE_KEY"),
            alipay_public_key_string=os.environ.get("ALIPAY_PUBLIC_KEY"),
            sign_type="RSA2",
            debug=False  # 生产环境用 False，沙箱用 True
        )
    
    def generate_order_no(self) -> str:
        """生成商户订单号"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        random_str = ''.join(random.choices(string.digits, k=6))
        return f"{timestamp}{random_str}"
    
    def create_qr_code_order(self, out_trade_no: str, total_amount: float, 
                              subject: str, body: str) -> dict:
        """
        创建当面付二维码订单
        返回二维码链接，用户扫码支付
        """
        order = self.alipay.api_alipay_trade_precreate(
            out_trade_no=out_trade_no,
            total_amount=total_amount,
            subject=subject,
            body=body,
            timeout_express="30m"  # 30分钟未支付自动关闭
        )
        
        if order.get("code") == "10000":
            return {
                "out_trade_no": out_trade_no,
                "qr_code": order.get("qr_code"),  # 二维码内容
                "success": True
            }
        else:
            raise Exception(f"创建订单失败: {order.get('msg')}")
    
    def query_order(self, out_trade_no: str) -> dict:
        """查询订单状态"""
        result = self.alipay.api_alipay_trade_query(out_trade_no=out_trade_no)
        return result