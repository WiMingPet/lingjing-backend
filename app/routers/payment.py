@router.post("/create_order")
def create_order(
    request: CreateOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create Alipay WAP payment order"""
    service = PaymentService()
    # ✅ 调用新的 wap 支付方法
    pay_url = service.create_wap_pay_order(
        out_trade_no=service.generate_order_no(),
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