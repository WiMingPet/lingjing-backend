"""
微信支付服务
"""
import json
import time
import random
import string
import hashlib
import os
from app.config import settings
from wechatpayv3 import WeChatPay, WeChatPayType


class WeChatPayService:
    def __init__(self):
        # 从挂载的文件读 PEM
        private_key = self._load_pem(
            file_path="/app/wechat_private_key.pem",
            env_value=settings.WECHAT_PRIVATE_KEY,
        )
        public_key = self._load_pem(
            file_path="/app/wechat_public_key.pem",
            env_value=settings.WECHAT_PUBLIC_KEY,
        )

        self.wxpay = WeChatPay(
            wechatpay_type=WeChatPayType.APP,
            mchid=settings.WECHAT_MCHID,
            private_key=private_key,
            cert_serial_no=settings.WECHAT_CERT_SERIAL,
            apiv3_key=settings.WECHAT_APIV3_KEY,
            appid=settings.WECHAT_APPID,
            notify_url="https://api.lingjing-media.com/api/payment/wechat_notify",
            public_key=public_key,
            public_key_id=settings.WECHAT_PUBLIC_KEY_ID,
        )

    def _load_pem(self, file_path: str, env_value: str) -> str:
        """优先从文件读，没有就从环境变量读"""
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                return f.read()
        # 从环境变量读，处理 \n
        if env_value:
            return env_value.replace("\\n", "\n") if "\\n" in env_value else env_value
        return ""

    def create_app_order(self, out_trade_no: str, total_fee: int, description: str) -> dict:
        code, message = self.wxpay.pay(
            description=description,
            out_trade_no=out_trade_no,
            amount={"total": total_fee},
        )

        if code != 200:
            raise Exception(f"微信下单失败: {message}")

        result = json.loads(message) if isinstance(message, str) else message
        prepay_id = result.get("prepay_id")
        if not prepay_id:
            raise Exception(f"微信返回没有 prepay_id: {result}")

        return self._sign_app_pay_params(prepay_id)

    def _sign_app_pay_params(self, prepay_id: str) -> dict:
        appid = settings.WECHAT_APPID
        partnerid = settings.WECHAT_MCHID
        package = "Sign=WXPay"
        noncestr = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
        timestamp = str(int(time.time()))

        params = {
            "appid": appid,
            "noncestr": noncestr,
            "package": package,
            "partnerid": partnerid,
            "prepayid": prepay_id,
            "timestamp": timestamp,
        }

        sign_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        sign_str += f"&key={settings.WECHAT_APIV2_KEY}"
        sign = hashlib.md5(sign_str.encode("utf-8")).hexdigest().upper()

        return {
            "appid": appid,
            "partnerid": partnerid,
            "prepayid": prepay_id,
            "package": package,
            "noncestr": noncestr,
            "timestamp": timestamp,
            "sign": sign,
        }

    def verify_callback(self, headers: dict, body: bytes) -> dict:
        return self.wxpay.callback(headers, body)


wechat_pay_service = WeChatPayService()