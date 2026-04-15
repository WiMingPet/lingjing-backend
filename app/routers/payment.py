from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app.schemas.payment import CreateOrderRequest
from app.models.user import User
from app.services.payment_service import PaymentService
from app.utils.auth import get_current_user
from app.models.order import RechargeOrder
import logging
import os

router = APIRouter(prefix="/payment", tags=["payment"])
logger = logging.getLogger(__name__)


@router.post("/create_order")
def create_order(
    request: CreateOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create Alipay WAP payment order"""
    service = PaymentService()
    
    # 先生成订单号
    out_trade_no = service.generate_order_no()
    # 保存订单到数据库
    order = RechargeOrder(
        order_no=out_trade_no,
        user_id=current_user.id,
        amount=request.amount,
        credits=request.credits,
        status="pending"
    )
    db.add(order)
    db.commit()
    
    pay_url = service.create_wap_pay_order(
        out_trade_no=out_trade_no,
        total_amount=request.amount,
        subject=f"Credits Recharge - {request.credits} credits",
        body=f"Purchase {request.credits} credits",
        return_url=os.environ.get("ALIPAY_RETURN_URL", "https://lingji.preview.aliyun-zeabur.cn/payment/result")
    )

    return {
        "order_id": out_trade_no,
        "pay_url": pay_url,
        "amount": request.amount
    }


@router.get("/order_status/{order_id}")
def get_order_status(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Query order payment status"""
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
    
    form_data = await request.form()
    data = dict(form_data)
    
    logger.info(f"收到支付宝回调: {data}")
    
    # 使用 PaymentService 中的支付宝客户端（已经正确初始化）
    service = PaymentService()
    alipay = service.alipay
    
    # 验证签名
    sign = data.pop('sign', None)
    if not alipay.verify(data, sign):
        logger.error("签名验证失败")
        return "fail"
    
    # 检查交易状态
    trade_status = data.get('trade_status')
    out_trade_no = data.get('out_trade_no')
    
    if trade_status == 'TRADE_SUCCESS':
        # 查询订单
        order = db.query(RechargeOrder).filter(RechargeOrder.order_no == out_trade_no).first()
        if not order:
            logger.error(f"订单 {out_trade_no} 不存在")
            return "fail"
        
        if order.status == 'paid':
            logger.info(f"订单 {out_trade_no} 已处理过")
            return "success"
        
        # 更新用户灵境点
        user = db.query(User).filter(User.id == order.user_id).first()
        if user:
            user.credits += order.credits
            logger.info(f"用户 {user.id} 灵境点增加 {order.credits}，当前余额: {user.credits}")
        else:
            logger.error(f"用户 {order.user_id} 不存在")
            return "fail"
        
        # 更新订单状态
        order.status = 'paid'
        order.paid_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"订单 {out_trade_no} 处理完成")
        
    return "success"