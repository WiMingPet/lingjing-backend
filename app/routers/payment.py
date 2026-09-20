import logging
import time
import jwt
import requests as sync_requests
import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.order import RechargeOrder
from app.models.user import User
from app.schemas.payment import CreateOrderRequest, CreateOrderResponse, OrderStatusResponse
from app.schemas.task import APIResponse
from app.services.payment_service import PaymentService
from app.services.wechat_pay_service import wechat_pay_service
from app.utils.auth import get_current_user
from app.config import settings

router = APIRouter(prefix="/payment", tags=["payment"])
logger = logging.getLogger(__name__)

def _is_mobile_client(user_agent: str) -> bool:
    user_agent = user_agent.lower()
    mobile_keywords = [
        "mobile", "android", "iphone", "ipad", "ipod", "phone",
        "webos", "blackberry", "opera mini", "iemobile", "symbian",
        "edg", "edge",  # Edge 移动版也包含这些关键字
        "mqqbrowser", "ucbrowser", "micromessenger", "wechat"
    ]
    # 额外排除：包含 "mobile" 但明确是桌面版的不算
    if "mobile" in user_agent and "desktop" not in user_agent:
        return True
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
    user_agent = http_request.headers.get("user-agent", "").lower()

    # 渠道判断
    if not channel:
        if "expo" in user_agent or "lingjing" in user_agent:
            channel = "app_native"
        elif _is_mobile_client(user_agent):
            channel = "mobile_wap"
        else:
            channel = "pc_qr"

    try:
        # ========== APP原生支付 ==========
        if channel == "app_native":
            order_info = service.create_app_order(
                out_trade_no=order_no,
                total_amount=payload.amount,
                subject=subject,
                body=body,
            )
            return CreateOrderResponse(
                order_no=order_no,
                channel="app_native",
                order_info=order_info,
                amount=payload.amount,
                credits=payload.credits,
                status="pending",
            )

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

        # 兜底：PC二维码
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

    
# ========== IAP 苹果支付验证 ==========
@router.post("/iap_verify")
async def verify_iap_receipt(
    request: Request,
    db: Session = Depends(get_db)
):
    body = await request.json()
    logger.info(f"[IAP-VERIFY] 收到请求")
    
    jws = body.get("jws_representation", "")
    credits = body.get("credits", 0)
    user_id = body.get("user_id", None)
    
    if not jws:
        raise HTTPException(status_code=400, detail="缺少支付凭证")
    if not user_id:
        raise HTTPException(status_code=400, detail="缺少用户ID")
    
    # ========== 读取私钥 ==========
    private_key = ""
    key_path = Path("/app/JWT.P8/SubscriptionKey_7D2S3326TF.p8")
    if not key_path.exists():
        key_path = Path(__file__).parent.parent.parent / "JWT.P8" / "SubscriptionKey_7D2S3326TF.p8"

    if key_path.exists():
        with open(key_path, "r") as f:
            private_key = f.read()
        logger.info(f"[IAP-VERIFY] 私钥读取成功")
    else:
        raise HTTPException(status_code=500, detail="私钥文件不存在")
    
    # ========== 2. 生成 JWT ==========
    try:
        ISSUER_ID = "cc9a7145-e0d9-4aa1-b9cb-3c97b4967d58"
        KEY_ID = "7D2S3326TF"
        BUNDLE_ID = "com.lingjing-media.app"
        
        now = int(time.time())
        payload = {
            "iss": ISSUER_ID,
            "iat": now,
            "exp": now + 3600,
            "aud": "appstoreconnect-v1",
            "bid": BUNDLE_ID,
        }
        headers = {"alg": "ES256", "kid": KEY_ID, "typ": "JWT"}
        
        token = jwt.encode(payload, private_key, algorithm="ES256", headers=headers)
        logger.info(f"[IAP-VERIFY] JWT 生成成功")
    except Exception as e:
        logger.error(f"[IAP-VERIFY] JWT 生成失败: {e}")
        raise HTTPException(status_code=500, detail=f"服务器配置错误: {e}")
    
    # ========== 3. 解析 JWS ==========
    import base64
    import json
    try:
        parts = jws.split('.')
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += '=' * padding
        jws_payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode('utf-8'))
        
        transaction_id = jws_payload.get("transactionId")
        product_id = jws_payload.get("productId")
        environment = jws_payload.get("environment")
        bundle_id = jws_payload.get("bundleId")
        
        logger.info(f"[IAP-VERIFY] JWS: tx={transaction_id}, product={product_id}, env={environment}")
    except Exception as e:
        logger.error(f"[IAP-VERIFY] JWS 解析失败: {e}")
        raise HTTPException(status_code=400, detail=f"凭证解析失败: {e}")
    
    if not transaction_id:
        raise HTTPException(status_code=400, detail="缺少交易ID")
    
    # ========== 4. 校验 bundleId 和 productId ==========
    if bundle_id != "com.lingjing-media.app":
        raise HTTPException(status_code=400, detail="Bundle ID 不匹配")
    
    expected_products = [
        "com.lingjing_media.app.credits_100",
        "com.lingjing_media.app.credits_350",
        "com.lingjing_media.app.credits_900",
        "com.lingjing_media.app.credits_2000"
    ]
    if product_id not in expected_products:
        raise HTTPException(status_code=400, detail="商品ID无效")
    
    # ========== 5. 调用 App Store Server API ==========
    try:
        if environment == "Sandbox":
            api_base = "https://api.storekit-sandbox.itunes.apple.com"
        else:
            api_base = "https://api.storekit.itunes.apple.com"
        
        api_url = f"{api_base}/inApps/v1/transactions/{transaction_id}"
        resp = sync_requests.get(api_url, headers={"Authorization": f"Bearer {token}"})
        
        if resp.status_code != 200:
            logger.error(f"[IAP-VERIFY] Apple API 返回 {resp.status_code}: {resp.text}")
            raise HTTPException(status_code=400, detail=f"Apple 验证失败: {resp.status_code}")
        
        logger.info(f"[IAP-VERIFY] Apple API 验证成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[IAP-VERIFY] Apple API 调用失败: {e}")
        raise HTTPException(status_code=500, detail=f"Apple API 调用失败: {e}")
    
    # ========== 6. 防重复 ==========
    existing = db.query(RechargeOrder).filter(
        RechargeOrder.order_no == f"iap_{transaction_id}"
    ).first()
    if existing:
        user = db.query(User).filter(User.id == user_id).first()
        return {"code": 200, "message": "已充值", "credits": user.credits if user else 0}
    
    # ========== 7. 加灵境点 ==========
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    user.credits += credits
    db.commit()
    
    order = RechargeOrder(
        order_no=f"iap_{transaction_id}",
        user_id=user_id,
        amount=0,
        credits=credits,
        status="paid",
    )
    db.add(order)
    db.commit()
    
    logger.info(f"[IAP-VERIFY] 用户 {user_id} 充值 {credits} 点，当前余额 {user.credits}")
    return {"code": 200, "message": "充值成功", "credits": user.credits}

    

@router.post("/wechat/create_order", response_model=APIResponse)
async def create_wechat_order(
    payload: CreateOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """微信 APP 支付统一下单"""
    import datetime
    import random
    order_no = "WX" + datetime.datetime.now().strftime("%Y%m%d%H%M%S") + str(random.randint(1000, 9999))

    order = RechargeOrder(
        order_no=order_no,
        user_id=current_user.id,
        amount=float(payload.amount),
        credits=payload.credits,
        status="pending",
    )
    db.add(order)
    db.commit()

    try:
        pay_params = wechat_pay_service.create_app_order(
            out_trade_no=order_no,
            total_fee=int(float(payload.amount) * 100),
            description=f"灵境点充值 {payload.credits} 点",
        )

        return APIResponse(
            code=200,
            message="下单成功",
            data={
                "order_no": order_no,
                "pay_params": pay_params,
            }
        )
    except Exception as e:
        print(f"[WECHAT_PAY] 下单失败: {e}")
        raise HTTPException(500, f"微信下单失败: {e}")


@router.post("/wechat_notify")
async def wechat_notify(request: Request, db: Session = Depends(get_db)):
    """微信支付回调"""
    try:
        body = await request.body()
        headers = {k: v for k, v in request.headers.items()}

        result = wechat_pay_service.verify_callback(headers, body)

        if not result:
            print("[WECHAT_PAY] 回调验证失败")
            return JSONResponse({"code": "FAIL", "message": "验证失败"})

        event_type = result.get("event_type")
        if event_type != "TRANSACTION.SUCCESS":
            print(f"[WECHAT_PAY] 非支付成功事件: {event_type}")
            return JSONResponse({"code": "SUCCESS", "message": "成功"})

        resource = result.get("resource", {})
        decrypted = wechat_pay_service.wxpay.decrypt_callback(resource)

        out_trade_no = decrypted.get("out_trade_no")
        transaction_id = decrypted.get("transaction_id")
        trade_state = decrypted.get("trade_state")

        print(f"[WECHAT_PAY] 支付回调: order_no={out_trade_no}, txn={transaction_id}, state={trade_state}")

        if trade_state != "SUCCESS":
            return JSONResponse({"code": "SUCCESS", "message": "成功"})

        order = db.query(RechargeOrder).filter(RechargeOrder.order_no == out_trade_no).first()
        if not order:
            print(f"[WECHAT_PAY] 订单不存在: {out_trade_no}")
            return JSONResponse({"code": "FAIL", "message": "订单不存在"})

        if order.status == "paid":
            print(f"[WECHAT_PAY] 订单已处理: {out_trade_no}")
            return JSONResponse({"code": "SUCCESS", "message": "成功"})

        order.status = "paid"
        user = db.query(User).filter(User.id == order.user_id).first()
        if user:
            user.credits += order.credits
            print(f"[WECHAT_PAY] 用户 {user.id} 充值 {order.credits} 点，当前 {user.credits}")
        db.commit()

        return JSONResponse({"code": "SUCCESS", "message": "成功"})

    except Exception as e:
        import traceback
        print(f"[WECHAT_PAY] 回调处理失败: {e}")
        print(traceback.format_exc())
        return JSONResponse({"code": "FAIL", "message": str(e)})


# ========== 管理员充值接口（内部使用） ==========
@router.post("/admin_add_credits")
async def admin_add_credits(
    phone: str,
    credits: int,
    admin_key: str,
    db: Session = Depends(get_db),
):
    """
    管理员给指定手机号充值点数
    调用时需要提供 admin_key 进行安全校验
    """
    ADMIN_KEY = os.getenv("ADMIN_KEY", "lingjing-admin-20260906")
    
    if admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="管理员密钥错误")
    
    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    user.credits += credits
    db.commit()
    
    print(f"[ADMIN] 给用户 {phone} 充值 {credits} 点，当前余额 {user.credits}")
    return {
        "code": 200,
        "message": f"已给 {phone} 充值 {credits} 点",
        "current_credits": user.credits
    }

# ========== 管理员查询用户余额 ==========
@router.get("/admin_query_credits")
async def admin_query_credits(
    phone: str,
    admin_key: str,
    db: Session = Depends(get_db),
):
    """
    管理员查询指定手机号的余额
    调用时需要提供 admin_key 进行安全校验
    """
    ADMIN_KEY = os.getenv("ADMIN_KEY", "lingjing-admin-20260906")
    
    if admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="管理员密钥错误")
    
    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    print(f"[ADMIN] 查询用户 {phone} 余额: {user.credits} 点")
    return {
        "code": 200,
        "message": "查询成功",
        "data": {
            "phone": user.phone,
            "user_id": user.id,
            "credits": user.credits
        }
    }

@router.get("/admin_query_history")
async def admin_query_history(
    phone: str,
    admin_key: str,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """
    管理员查询用户最近的消费记录
    """
    ADMIN_KEY = os.getenv("ADMIN_KEY", "lingjing-admin-20260906")
    
    if admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="管理员密钥错误")
    
    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    from app.models.history import History
    records = db.query(History).filter(
        History.user_id == user.id
    ).order_by(History.created_at.desc()).limit(limit).all()
    
    return {
        "code": 200,
        "message": "查询成功",
        "data": {
            "phone": phone,
            "current_credits": user.credits,
            "records": [
                {
                    "id": r.id,
                    "type": r.type,
                    "url": r.url,
                    "created_at": r.created_at.isoformat() if r.created_at else None
                }
                for r in records
            ]
        }
    }

@router.get("/admin_query_user_by_id")
async def admin_query_user_by_id(
    user_id: int,
    admin_key: str,
    db: Session = Depends(get_db),
):
    """管理员按用户ID查询用户信息"""
    ADMIN_KEY = os.getenv("ADMIN_KEY", "lingjing-admin-20260906")
    
    if admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="管理员密钥错误")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    return {
        "code": 200,
        "message": "查询成功",
        "data": {
            "user_id": user.id,
            "phone": user.phone,
            "credits": user.credits
        }
    }