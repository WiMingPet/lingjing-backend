import os
import random
import string
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict

from alipay import AliPay
from sqlalchemy.orm import Session

from app.models.order import RechargeOrder
from app.models.user import User


class PaymentService:
    def __init__(self) -> None:
        app_private_key_string = self._load_key(
            file_env="ALIPAY_PRIVATE_KEY_PATH",
            default_file_path="/app/alipay_private_key.pem",
            key_env="ALIPAY_PRIVATE_KEY",
        )
        alipay_public_key_string = self._load_key(
            file_env="ALIPAY_PUBLIC_KEY_PATH",
            default_file_path="/app/alipay_public_key.pem",
            key_env="ALIPAY_PUBLIC_KEY",
        )
        self.alipay_app_id = os.getenv("ALIPAY_APP_ID", "")
        self.notify_url = os.getenv("ALIPAY_NOTIFY_URL", "")
        self.seller_id = os.getenv("ALIPAY_SELLER_ID", "")
        self.gateway = os.getenv("ALIPAY_GATEWAY", "https://openapi.alipay.com/gateway.do")

        self.alipay = AliPay(
            appid=self.alipay_app_id,
            app_notify_url=self.notify_url,
            app_private_key_string=app_private_key_string,
            alipay_public_key_string=alipay_public_key_string,
            sign_type="RSA2",
            debug=False,
        )

    def _load_key(self, file_env: str, default_file_path: str, key_env: str) -> str:
        file_path = os.getenv(file_env, default_file_path)
        if file_path and os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as file:
                value = file.read()
        else:
            value = os.getenv(key_env, "")
        return value.replace("\\n", "\n").strip()

    def generate_order_no(self) -> str:
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        random_part = "".join(random.choices(string.digits, k=8))
        return f"R{timestamp}{random_part}"

    def create_pc_qr_order(self, out_trade_no: str, total_amount: Decimal, subject: str, body: str) -> str:
        result = self.alipay.api_alipay_trade_precreate(
            out_trade_no=out_trade_no,
            total_amount=str(total_amount),
            subject=subject,
            body=body,
            timeout_express="30m",
            notify_url=self.notify_url,
        )
        if result.get("code") != "10000" or not result.get("qr_code"):
            raise ValueError(f"alipay.trade.precreate failed: {result}")
        return result["qr_code"]

    def create_mobile_wap_order(
        self,
        out_trade_no: str,
        total_amount: Decimal,
        subject: str,
        body: str,
        return_url: str,
    ) -> str:
        order_string = self.alipay.api_alipay_trade_wap_pay(
            out_trade_no=out_trade_no,
            total_amount=str(total_amount),
            subject=subject,
            body=body,
            return_url=return_url,
            notify_url=self.notify_url,
        )
        return f"{self.gateway}?{order_string}"

    def verify_notification(self, notify_data: Dict[str, Any]) -> bool:
        data = dict(notify_data)
        sign = data.pop("sign", None)
        if not sign:
            return False
        return self.alipay.verify(data, sign)

    def process_paid_notification(self, db: Session, notify_data: Dict[str, Any]) -> bool:
        out_trade_no = notify_data.get("out_trade_no")
        trade_status = notify_data.get("trade_status")
        if not out_trade_no or trade_status not in {"TRADE_SUCCESS", "TRADE_FINISHED"}:
            return True

        order = db.query(RechargeOrder).filter(RechargeOrder.order_no == out_trade_no).first()
        if not order:
            return False
        if order.status == "paid":
            return True

        if not self._validate_notification_business_fields(order, notify_data):
            return False

        user = db.query(User).filter(User.id == order.user_id).first()
        if not user:
            return False

        user.credits += order.credits
        order.status = "paid"
        order.paid_at = datetime.utcnow()
        db.add(user)
        db.add(order)
        db.commit()
        return True

    def _validate_notification_business_fields(self, order: RechargeOrder, notify_data: Dict[str, Any]) -> bool:
        if self.alipay_app_id and notify_data.get("app_id") and notify_data.get("app_id") != self.alipay_app_id:
            return False
        if self.seller_id and notify_data.get("seller_id") and notify_data.get("seller_id") != self.seller_id:
            return False
        total_amount = notify_data.get("total_amount")
        if total_amount is None:
            return False
        try:
            notified = Decimal(str(total_amount)).quantize(Decimal("0.01"))
            ordered = Decimal(str(order.amount)).quantize(Decimal("0.01"))
        except Exception:
            return False
        return notified == ordered

    def query_order(self, out_trade_no: str) -> Dict[str, Any]:
        return self.alipay.api_alipay_trade_query(out_trade_no=out_trade_no)