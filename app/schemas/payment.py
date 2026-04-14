from pydantic import BaseModel

class CreateOrderRequest(BaseModel):
    package_id: int
    amount: float
    credits: int

class CreateOrderResponse(BaseModel):
    order_id: str
    pay_url: str
    amount: float