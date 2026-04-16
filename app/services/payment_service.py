import logging
import os
import random
import string
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, Optional

from alipay import AliPay


logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self) -> None:
        self.app_id = os.getenv("ALIPAY_APP_ID", "").strip()
        self.notify_url = os.getenv("ALIPAY_NOTIFY_URL", "").strip()
        self.return_url = os.getenv("ALIPAY_RETURN_URL", "").strip()
        self.quit_url = os.getenv("ALIPAY_QUIT_URL", self.return_url).strip()
        self.gateway = self._get_gateway_url()
        self.alipay = AliPay(
            appid=self.app_id,
            app_notify_url=self.notify_url,
            app_private_key_string=self._load_key(
                env_name="ALIPAY_PRIVATE_KEY",
                default_paths=["/app/alipay_private_key.pem", "./certs/alipay_private_key.pem"],
            ),
            alipay_public_key_string=self._load_key(
                env_name="ALIPAY_PUBLIC_KEY",
                default_paths=["/app/alipay_public_key.pem", "./certs/alipay_public_key.pem"],
            ),
            sign_type="RSA2",
            debug=self.gateway != "https://openapi.alipay.com/gateway.do",
        )

    def _load_key(self, env_name: str, default_paths: list[str]) -> str:
        env_value = os.getenv(env_name, "").strip()
        if env_value:
            return env_value.replace("\\n", "\n")

        for path in default_paths:
            key_path = Path(path)
            if key_path.exists():
                return key_path.read_text(encoding="utf-8").strip()

        raise ValueError(f"缺少支付宝配置: {env_name}")

    def _get_gateway_url(self) -> str:
        configured_gateway = os.getenv("ALIPAY_GATEWAY", "").strip()
        if configured_gateway:
            return configured_gateway

        is_sandbox = os.getenv("ALIPAY_DEBUG", "false").lower() in {"1", "true", "yes"}
        if is_sandbox:
            return "https://openapi-sandbox.dl.alipaydev.com/gateway.do"
        return "https://openapi.alipay.com/gateway.do"

    def _amount_to_str(self, amount: Decimal | float | str) -> str:
        decimal_amount = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return format(decimal_amount, ".2f")

    def generate_order_no(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_str = "".join(random.choices(string.digits, k=6))
        return f"{timestamp}{random_str}"

    def create_pc_qr_order(
        self,
        out_trade_no: str,
        total_amount: Decimal | float | str,
        subject: str,
        body: str,
    ) -> str:
        response = self.alipay.api_alipay_trade_precreate(
            out_trade_no=out_trade_no,
            total_amount=self._amount_to_str(total_amount),
            subject=subject,
            body=body,
            notify_url=self.notify_url,
            timeout_express="30m",
        )

        if response.get("code") != "10000" or not response.get("qr_code"):
            raise ValueError(
                f"支付宝预下单失败: code={response.get('code')} sub_msg={response.get('sub_msg') or response.get('msg')}"
            )

        return response["qr_code"]

    def create_mobile_wap_order(
        self,
        out_trade_no: str,
        total_amount: Decimal | float | str,
        subject: str,
        body: str,
        return_url: Optional[str] = None,
        quit_url: Optional[str] = None,
    ) -> str:
        order_string = self.alipay.api_alipay_trade_wap_pay(
            out_trade_no=out_trade_no,
            total_amount=self._amount_to_str(total_amount),
            subject=subject,
            body=body,
            return_url=return_url or self.return_url,
            notify_url=self.notify_url,
            quit_url=quit_url or self.quit_url,
        )
        return f"{self.gateway}?{order_string}"

    def query_order(self, out_trade_no: str) -> Dict[str, Any]:
        return self.alipay.api_alipay_trade_query(out_trade_no=out_trade_no)

    def close_order(self, out_trade_no: str) -> Dict[str, Any]:
        return self.alipay.api_alipay_trade_close(out_trade_no=out_trade_no)

    def verify_notify(self, data: Dict[str, Any], sign: Optional[str]) -> bool:
        if not sign:
            return False
        return self.alipay.verify(data, sign)

    def validate_notify_payload(self, payload: Dict[str, Any], expected_amount: Decimal | float | str) -> None:
        notify_app_id = str(payload.get("app_id", "")).strip()
        if notify_app_id and self.app_id and notify_app_id != self.app_id:
            raise ValueError("支付宝通知中的 app_id 与商户配置不一致")

        notify_amount = self._amount_to_str(payload.get("total_amount", "0"))
        order_amount = self._amount_to_str(expected_amount)
        if notify_amount != order_amount:
            raise ValueError("支付宝通知中的 total_amount 与订单金额不一致")

    def build_subject(self, credits: int) -> str:
        return f"灵境AI创意平台充值 - {credits} 灵境点"

    def build_body(self, credits: int) -> str:
        return f"用户充值 {credits} 灵境点"