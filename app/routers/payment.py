from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
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
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/payment", tags=["payment"])
logger = logging.getLogger(__name__)


@router.post("/create_order")
def create_order(
    request: CreateOrderRequest,
    http_request: Request,  # 这个参数必须有
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建支付宝支付订单（自动选择支付方式）"""
    service = PaymentService()
    out_trade_no = service.generate_order_no()
    
    # 保存订单
    order = RechargeOrder(
        order_no=out_trade_no,
        user_id=current_user.id,
        amount=request.amount,
        credits=request.credits,
        status="pending"
    )
    db.add(order)
    db.commit()
    
    # 判断设备类型
    user_agent = http_request.headers.get("user-agent", "").lower()
    is_mobile = any(x in user_agent for x in ["mobile", "android", "iphone", "ipad", "phone"])
    
    if is_mobile:
        # 手机端：使用 WAP 支付（跳转支付宝）
        pay_url = service.create_wap_pay_order(
            out_trade_no=out_trade_no,
            total_amount=request.amount,
            subject=f"Credits Recharge - {request.credits} credits",
            body=f"Purchase {request.credits} credits",
            return_url=os.environ.get("ALIPAY_RETURN_URL", "https://lingji.preview.aliyun-zeabur.cn/payment/result")
        )
        return {
            "pay_url": pay_url,
            "type": "wap"
        }
    else:
        # 电脑端：使用当面付（二维码）
        qr_code = service.create_qr_code_order(
            out_trade_no=out_trade_no,
            total_amount=request.amount,
            subject=f"Credits Recharge - {request.credits} credits",
            body=f"Purchase {request.credits} credits"
        )
        return {
            "qr_code": qr_code,
            "type": "qr_code"
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
    logger.info(f"trade_status: {data.get('trade_status')}")
    logger.info(f"out_trade_no: {data.get('out_trade_no')}")
    
    # 使用 PaymentService 中的支付宝客户端
    service = PaymentService()
    alipay = service.alipay
    
    # 验证签名
    sign = data.pop('sign', None)
    logger.info(f"签名验证中...")
    if not alipay.verify(data, sign):
        logger.error("签名验证失败")
        return "fail"
    
    logger.info("签名验证成功")
    
    # 检查交易状态
    trade_status = data.get('trade_status')
    out_trade_no = data.get('out_trade_no')
    
    if trade_status == 'TRADE_SUCCESS':
        logger.info(f"订单 {out_trade_no} 支付成功，开始处理")
        
        # 查询订单
        order = db.query(RechargeOrder).filter(RechargeOrder.order_no == out_trade_no).first()
        if not order:
            logger.error(f"订单 {out_trade_no} 不存在")
            return "fail"
        
        logger.info(f"订单状态: {order.status}")
        
        if order.status == 'paid':
            logger.info(f"订单 {out_trade_no} 已处理过")
            return "success"
        
        # 更新用户灵境点
        user = db.query(User).filter(User.id == order.user_id).first()
        if user:
            old_credits = user.credits
            user.credits += order.credits
            logger.info(f"用户 {user.id} 灵境点从 {old_credits} 增加到 {user.credits}")
        else:
            logger.error(f"用户 {order.user_id} 不存在")
            return "fail"
        
        # 更新订单状态
        order.status = 'paid'
        order.paid_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"订单 {out_trade_no} 处理完成")
    else:
        logger.info(f"交易状态不是 TRADE_SUCCESS，而是 {trade_status}")
        
    return "success"

@router.post("/create_order_html", response_class=HTMLResponse)
def create_order_html(
    request: CreateOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = PaymentService()
    out_trade_no = service.generate_order_no()
    
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
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>正在跳转支付宝...</title>
    </head>
    <body>
        <form id="alipayForm" action="{pay_url}" method="POST">
            <input type="submit" value="跳转支付宝支付" style="display:none">
        </form>
        <script>
            document.getElementById('alipayForm').submit();
        </script>
        <p>正在跳转支付宝，请稍候...</p>
        <p>如未跳转，请<a href="{pay_url}">点击这里</a>。</p>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)