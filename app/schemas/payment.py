from pydantic import BaseModel
from typing import Optional

class CreateOrderRequest(BaseModel):
    package_id: int  # 套餐ID
    amount: float    # 金额
    credits: int     # 灵境点数量

class CreateOrderResponse(BaseModel):
    order_id: str           # 商户订单号
    qr_code: str            # 二维码内容（二维码链接）
    amount: float