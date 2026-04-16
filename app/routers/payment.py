import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.order import RechargeOrder
from app.models.user import User
from app.schemas.payment import (
    CreateOrderRequest,
    MobileCreateOrderResponse,
    OrderStatusResponse,
    PcCreateOrderResponse,
)
from app.services.payment_service import PaymentService
from app.utils.auth import get_current_user


router = APIRouter(prefix="/payment", tags=["payment"])
logger = logging.getLogger(__name__)


def _create_recharge_order(
    db: Session,
    current_user: User,
    request: CreateOrderRequest,
    order_no: str,
) -> RechargeOrder:
    order = RechargeOrder(
        order_no=order_no,
        user_id=current_user.id,
        amount=float(request.amount),
        credits=request.credits,
        status="pending",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def _mark_order_paid(order: RechargeOrder, db: Session) -> RechargeOrder:
    if order.status == "paid":
        return order

    user = db.query(User).filter(User.id == order.user_id).first()
    if not user:
        raise HTTPException(status_code=500, detail="订单关联用户不存在")

    user.credits += order.credits
    order.status = "paid"
    order.paid_at = order.paid_at or datetime.utcnow()
    db.commit()
    db.refresh(order)
    return order


def _sync_order_status(order: RechargeOrder, service: PaymentService, db: Session) -> RechargeOrder:
    if order.status == "paid":
        return order

    result = service.query_order(order.order_no)
    if result.get("code") != "10000":
        return order

    trade_status = result.get("trade_status")
    if trade_status in {"TRADE_SUCCESS", "TRADE_FINISHED"} and order.status != "paid":
        order = _mark_order_paid(order=order, db=db)
    elif trade_status == "TRADE_CLOSED" and order.status == "pending":
        order.status = "closed"
        db.commit()
        db.refresh(order)

    return order


@router.post("/alipay/pc/create-order", response_model=PcCreateOrderResponse)
def create_pc_order(
    request: CreateOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """电脑端创建支付宝当面付二维码订单。"""
    service = PaymentService()
    order_no = service.generate_order_no()
    order = _create_recharge_order(db=db, current_user=current_user, request=request, order_no=order_no)
    qr_code = service.create_pc_qr_order(
        out_trade_no=order.order_no,
        total_amount=request.amount,
        subject=service.build_subject(request.credits),
        body=service.build_body(request.credits),
    )
    # 添加日志，确认生成了二维码
    logger.info(f"PC 订单 {order.order_no} 生成二维码，长度: {len(qr_code) if qr_code else 0}")
    return PcCreateOrderResponse(
        order_no=order.order_no,
        amount=request.amount,
        credits=request.credits,
        status=order.status,
        channel="pc_qr",
        qr_code=qr_code,
    )


@router.post("/alipay/mobile/create-order", response_model=MobileCreateOrderResponse)
def create_mobile_order(
    request: CreateOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手机端创建支付宝手机网站支付订单。"""
    service = PaymentService()
    order_no = service.generate_order_no()
    order = _create_recharge_order(db=db, current_user=current_user, request=request, order_no=order_no)
    pay_url = service.create_mobile_wap_order(
        out_trade_no=order.order_no,
        total_amount=request.amount,
        subject=service.build_subject(request.credits),
        body=service.build_body(request.credits),
    )
    return MobileCreateOrderResponse(
        order_no=order.order_no,
        amount=request.amount,
        credits=request.credits,
        status=order.status,
        channel="mobile_wap",
        pay_url=pay_url,
    )


@router.post("/create_order")
def create_order_by_user_agent(
    request: CreateOrderRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """兼容旧接口，按 User-Agent 自动选择 PC 或手机支付。"""
    user_agent = http_request.headers.get("user-agent", "").lower()
    
    # 定义更严谨的手机设备关键词
    mobile_keywords = ["mobile", "android", "iphone", "ipad", "phone", "blackberry", "windows phone"]
    is_mobile = any(keyword in user_agent for keyword in mobile_keywords)
    
    # 额外检查：如果用户代理包含 "windows" 或 "mac" 且没有移动设备关键词，则判定为电脑
    is_pc = ("windows" in user_agent or "mac" in user_agent or "linux" in user_agent) and not is_mobile
    
    logger.info(f"User-Agent: {user_agent[:200]}, is_mobile: {is_mobile}, is_pc: {is_pc}")
    
    if is_pc:
        # 电脑端：调用 PC 支付接口
        return create_pc_order(request=request, db=db, current_user=current_user)
    else:
        # 手机端：调用手机支付接口
        return create_mobile_order(request=request, db=db, current_user=current_user)


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
        raise HTTPException(status_code=404, detail="订单不存在")

    service = PaymentService()
    order = _sync_order_status(order=order, service=service, db=db)
    return OrderStatusResponse(
        order_no=order.order_no,
        status=order.status,
        amount=order.amount,
        credits=order.credits,
        paid_at=order.paid_at.isoformat() if order.paid_at else None,
    )


@router.post("/notify", response_class=PlainTextResponse)
async def alipay_notify(request: Request, db: Session = Depends(get_db)):
    """支付宝异步通知回调。"""
    service = PaymentService()
    form_data = await request.form()
    payload = {key: value for key, value in form_data.items()}
    sign = payload.pop("sign", None)
    payload.pop("sign_type", None)

    if not service.verify_notify(payload, sign):
        logger.warning("支付宝回调验签失败")
        return PlainTextResponse("fail")

    out_trade_no = str(payload.get("out_trade_no", "")).strip()
    if not out_trade_no:
        logger.warning("支付宝回调缺少 out_trade_no")
        return PlainTextResponse("fail")

    order = db.query(RechargeOrder).filter(RechargeOrder.order_no == out_trade_no).first()
    if not order:
        logger.warning("支付宝回调订单不存在: %s", out_trade_no)
        return PlainTextResponse("fail")

    try:
        service.validate_notify_payload(payload=payload, expected_amount=order.amount)
    except ValueError as exc:
        logger.warning("支付宝回调业务校验失败: %s", exc)
        return PlainTextResponse("fail")

    trade_status = str(payload.get("trade_status", "")).strip()
    if trade_status in {"TRADE_SUCCESS", "TRADE_FINISHED"}:
        if order.status != "paid":
            try:
                _mark_order_paid(order=order, db=db)
            except HTTPException:
                logger.error("支付成功但用户不存在: user_id=%s", order.user_id)
                return PlainTextResponse("fail")
            logger.info("订单支付成功并已加点: %s", out_trade_no)
        return PlainTextResponse("success")

    if trade_status == "TRADE_CLOSED" and order.status == "pending":
        order.status = "closed"
        db.commit()

    return PlainTextResponse("success")


@router.get("/create_order_html", response_class=HTMLResponse)
def create_order_html(
    package_id: int,
    amount: float,
    credits: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = CreateOrderRequest(package_id=package_id, amount=amount, credits=credits)
    response = create_mobile_order(request=request, db=db, current_user=current_user)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>正在跳转支付宝...</title>
    </head>
    <body>
        <script>
            window.location.replace("{response.pay_url}");
        </script>
        <p>正在跳转支付宝，请稍候...</p>
        <p>如未跳转，请<a href="{response.pay_url}">点击这里继续支付</a>。</p>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)