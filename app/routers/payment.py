from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app.schemas.payment import CreateOrderRequest, CreateOrderResponse
from app.models.user import User
from app.services.payment_service import PaymentService
from app.utils.auth import get_current_user
import logging
import os

router = APIRouter(prefix="/payment", tags=["支付"])
logger = logging.getLogger(__name__)


@router.post("/create_order")
def create_order(
    request: CreateOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建支付宝支付订单"""
    service = PaymentService()
    result = service.create_qr_code_order(
        out_trade_no=service.generate_order_no(),
        total_amount=request.amount,
        subject=f"灵境点充值 - {request.credits}点",
        body=f"购买{request.credits}灵境点"
    )
    
    return {
        "order_id": result["out_trade_no"],
        "qr_code": result["qr_code"],
        "amount": request.amount
    }


@router.get("/order_status/{order_id}")
def get_order_status(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """查询订单支付状态"""
    service = PaymentService()
    result = service.query_order(order_id)
    
    if result.get("code") == "10000":
        trade_status = result.get("trade_status")
        if trade_status == "TRADE_SUCCESS":
            return {"status": "paid", "credits": 0}
        elif trade_status == "WAIT_BUYER_PAY":
            return {"status": "pending"}
        elif trade_status == "TRADE_CLOSED":
            return {"status": "closed"}
    
    return {"status": "pending"}


@router.post("/notify")
async def alipay_notify(request: Request, db: Session = Depends(get_db)):
    """支付宝异步通知回调"""
    from alipay import AliPay
    
    form_data = await request.form()
    data = dict(form_data)
    
    logger.info(f"收到支付宝回调: {data}")
    
    # 初始化支付宝客户端
    alipay = AliPay(
        appid=os.environ.get("ALIPAY_APP_ID"),
        app_notify_url=os.environ.get("ALIPAY_NOTIFY_URL"),
        app_private_key_string=os.environ.get("ALIPAY_PRIVATE_KEY"),
        alipay_public_key_string=os.environ.get("ALIPAY_PUBLIC_KEY"),
        sign_type="RSA2",
        debug=False
    )
    
    # 验证签名
    sign = data.pop('sign', None)
    if not alipay.verify(data, sign):
        logger.error("签名验证失败")
        return "fail"
    
    # 检查交易状态
    trade_status = data.get('trade_status')
    out_trade_no = data.get('out_trade_no')
    
    if trade_status == 'TRADE_SUCCESS':
        logger.info(f"订单 {out_trade_no} 支付成功")
        # TODO: 根据订单号查找订单，更新用户灵境点余额
        
    return "success"