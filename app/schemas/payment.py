from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class CreateOrderRequest(BaseModel):
    package_id: Optional[int] = Field(default=None, description="充值套餐 ID")
    amount: Decimal = Field(..., gt=0, decimal_places=2, description="支付金额，单位元")
    credits: int = Field(..., gt=0, description="充值后增加的灵境点")


class PaymentOrderBaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_no: str
    amount: Decimal
    credits: int
    status: str


class PcCreateOrderResponse(PaymentOrderBaseResponse):
    channel: Literal["pc_qr"]
    qr_code: str
    qr_code_expires_in: int = Field(default=7200, description="二维码有效期，单位秒")


class MobileCreateOrderResponse(PaymentOrderBaseResponse):
    channel: Literal["mobile_wap"]
    pay_url: str


class OrderStatusResponse(BaseModel):
    order_no: str
    status: str
    amount: Decimal
    credits: int
    paid_at: Optional[str] = None