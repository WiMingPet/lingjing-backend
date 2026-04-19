import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.order import RechargeOrder
from app.models.user import User
from app.schemas.payment import CreateOrderRequest, CreateOrderResponse, OrderStatusResponse
from app.services.payment_service import PaymentService
from app.utils.auth import get_current_user

router = APIRouter(prefix="/payment", tags=["payment"])
logger = logging.getLogger(__name__)

def _is_mobile_client(user_agent: str) -> bool:
    user_agent = user_agent.lower()
    mobile_keywords = ["mobile", "android", "iphone", "ipad", "phone"]
    return any(keyword in user_agent for keyword in mobile_keywords)


@router.post("/create_order", response_model=CreateOrderResponse)
def create_order(
    payload: CreateOrderRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = PaymentService()
    order_no = service.generate_order_no()

    order = RechargeOrder(
        order_no=order_no,
        user_id=current_user.id,
        amount=float(payload.amount),
        credits=payload.credits,
        status="pending",
    )
    db.add(order)
    db.commit()

    subject = f"灵境点充值 {payload.credits} 点"
    body = f"用户 {current_user.id} 充值灵境点"
    channel = payload.channel
    if not channel:
        channel = "mobile_wap" if _is_mobile_client(http_request.headers.get("user-agent", "")) else "pc_qr"

    try:
        if channel == "mobile_wap":
            pay_url = service.create_mobile_wap_order(
                out_trade_no=order_no,
                total_amount=payload.amount,
                subject=subject,
                body=body,
                return_url=os.getenv("ALIPAY_RETURN_URL", ""),
            )
            return CreateOrderResponse(
                order_no=order_no,
                channel="mobile_wap",
                pay_url=pay_url,
                amount=payload.amount,
                credits=payload.credits,
                status="pending",
            )

        qr_code = service.create_pc_qr_order(
            out_trade_no=order_no,
            total_amount=payload.amount,
            subject=subject,
            body=body,
        )
        return CreateOrderResponse(
            order_no=order_no,
            channel="pc_qr",
            qr_code=qr_code,
            amount=payload.amount,
            credits=payload.credits,
            status="pending",
        )
    except Exception as exc:
        logger.exception("Create alipay order failed: %s", exc)
        raise HTTPException(status_code=500, detail="创建支付宝订单失败") from exc


@router.get("/order_status/{order_no}", response_model=OrderStatusResponse)
def get_order_status(
    order_no: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = (
        db.query(RechargeOrder)
        .filter(RechargeOrder.order_no == order_no, RechargeOrder.user_id == current_user.id)
        .first()
    )
    if not order:
        return OrderStatusResponse(order_no=order_no, status="not_found")
    if order.status not in {"pending", "paid", "closed"}:
        return OrderStatusResponse(order_no=order_no, status="pending")
    return OrderStatusResponse(order_no=order_no, status=order.status)


@router.post("/notify", response_class=PlainTextResponse)
async def alipay_notify(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    notify_data = {key: value for key, value in form_data.items()}
    
    # 添加日志，打印所有参数
    logger.info(f"支付宝回调参数: {notify_data}")
    
    # 尝试多种方式获取 out_trade_no
    out_trade_no = notify_data.get("out_trade_no") or notify_data.get("out_trade_no")
    if not out_trade_no:
        logger.error("无法获取订单号，回调参数: %s", notify_data)
        return PlainTextResponse("fail")
    
    service = PaymentService()

    if not service.verify_notification(notify_data):
        logger.warning(f"Alipay notify verify failed: out_trade_no={out_trade_no}")
        return PlainTextResponse("fail")

    handled = service.process_paid_notification(db, notify_data)
    if not handled:
        logger.error(f"Alipay notify process failed: out_trade_no={out_trade_no}")
        return PlainTextResponse("fail")
    
    logger.info(f"订单 {out_trade_no} 处理成功")
    return PlainTextResponse("success")