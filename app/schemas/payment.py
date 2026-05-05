from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class CreateOrderRequest(BaseModel):
    package_id: int = Field(..., description="充值套餐ID")
    amount: Decimal = Field(..., gt=0, description="支付金额，单位元")
    credits: int = Field(..., gt=0, description="充值后增加的灵境点")
    channel: Optional[Literal["pc_qr", "mobile_wap"]] = Field(
        default=None,
        description="可选支付通道。为空时由后端根据 User-Agent 自动判断",
    )

    @field_validator("amount")
    @classmethod
    def normalize_amount(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))


class CreateOrderResponse(BaseModel):
    order_no: str
    channel: Literal["pc_qr", "mobile_wap", "app_native"]  # 新增 app_native
    qr_code: Optional[str] = None
    pay_url: Optional[str] = None
    order_info: Optional[str] = None  # 新增：APP支付订单串
    amount: Decimal
    credits: int
    status: Literal["pending", "paid", "closed"] = "pending"


class OrderStatusResponse(BaseModel):
    order_no: str
    status: Literal["pending", "paid", "closed", "not_found"]