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
        
    def create_app_order(
        self,
        out_trade_no: str,
        total_amount: Decimal,
        subject: str,
        body: str,
    ) -> str:
        """
        创建支付宝APP支付订单
        返回 order_info 字符串，前端传给支付宝SDK唤起APP支付
        """
        order_string = self.alipay.api_alipay_trade_app_pay(
            out_trade_no=out_trade_no,
            total_amount=str(total_amount),
            subject=subject,
            body=body,
            notify_url=self.notify_url,
        )
        return order_string

    def verify_notification(self, notify_data: Dict[str, Any]) -> bool:
        data = dict(notify_data)
        sign = data.pop("sign", None)
        if not sign:
            return False
        return self.alipay.verify(data, sign)

    def process_paid_notification(self, db: Session, notify_data: Dict[str, Any]) -> bool:
        import logging
        logger = logging.getLogger(__name__)
    
        # 获取订单号（兼容多种字段名）
        out_trade_no = notify_data.get("out_trade_no") or notify_data.get("out_trade_no")
        trade_status = notify_data.get("trade_status")
    
        logger.info(f"处理回调: out_trade_no={out_trade_no}, trade_status={trade_status}")
    
        if not out_trade_no:
            logger.error("回调参数中没有订单号")
            return False
    
        if trade_status not in {"TRADE_SUCCESS", "TRADE_FINISHED"}:
            logger.info(f"交易状态不是成功状态: {trade_status}")
            return True

        # 查询订单
        order = db.query(RechargeOrder).filter(RechargeOrder.order_no == out_trade_no).first()
        if not order:
            logger.error(f"订单不存在: {out_trade_no}")
            return False
    
        if order.status == "paid":
            logger.info(f"订单 {out_trade_no} 已处理过")
            return True

        # 验证金额（可选）
        total_amount = notify_data.get("total_amount")
        if total_amount and abs(float(total_amount) - order.amount) > 0.01:
            logger.warning(f"金额不匹配: 订单 {order.amount}, 回调 {total_amount}")

        # 更新用户灵境点
        user = db.query(User).filter(User.id == order.user_id).first()
        if not user:
            logger.error(f"用户不存在: {order.user_id}")
            return False

        old_credits = user.credits
        user.credits += order.credits
        order.status = "paid"
        order.paid_at = datetime.utcnow()
    
        db.commit()
    
        logger.info(f"用户 {user.id} 灵境点从 {old_credits} 增加到 {user.credits}")
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