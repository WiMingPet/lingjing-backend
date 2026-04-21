"""
订单侠API服务
文件路径: app/services/dingdanxia.py
"""

import httpx
import os
import logging

logger = logging.getLogger(__name__)

# 从环境变量读取配置
DINGDANXIA_APIKEY = os.getenv("DINGDANXIA_APIKEY", "")
DINGDANXIA_IP = os.getenv("DINGDANXIA_IP", "61.160.192.99")
DINGDANXIA_HOST = os.getenv("DINGDANXIA_HOST", "api.tbk.dingdanxia.com")


def parse_douyin_command(command: str) -> dict:
    """
    解析抖音口令/链接
    
    参数:
        command: 用户输入的抖音商品链接或口令
        
    返回:
        成功时: {"success": True, "product_id": "xxx", "title": "xxx", "price": 49.99, ...}
        失败时: {"success": False, "error": "错误信息"}
    """
    
    # 检查 API Key
    if not DINGDANXIA_APIKEY:
        logger.error("DINGDANXIA_APIKEY 未配置")
        return {"success": False, "error": "系统配置错误：未配置订单侠API Key"}
    
    # 接口地址
    api_path = "/douyin/shareCommandParse"
    api_url = f"http://{DINGDANXIA_IP}{api_path}"
    
    headers = {
        "Host": DINGDANXIA_HOST,
        "Content-Type": "application/json",
    }
    
    payload = {
        "apikey": DINGDANXIA_APIKEY,
        "command": command
    }
    
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(api_url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"订单侠响应: {result}")
            
            # code=0 表示成功
            if result.get("code") == 0:
                data = result.get("data", {})
                price_fen = data.get("price", 0)
                
                return {
                    "success": True,
                    "product_id": data.get("product_id", ""),
                    "title": data.get("title", ""),
                    "price": price_fen / 100 if price_fen else 0,
                    "detail_url": data.get("detail_url", ""),
                    "promotable": data.get("promotable", False),
                }
            else:
                error_msg = result.get("msg", "未知错误")
                return {"success": False, "error": f"订单侠解析失败: {error_msg}"}
                
    except httpx.ConnectError:
        return {"success": False, "error": "网络连接失败，请稍后重试"}
    except httpx.TimeoutException:
        return {"success": False, "error": "请求超时，请稍后重试"}
    except Exception as e:
        return {"success": False, "error": f"解析失败: {str(e)}"}


# ========== 兼容 link_to_video 路由 ==========
def get_douyin_product_info(url: str) -> dict:
    """
    获取抖音商品信息（兼容旧接口）
    """
    result = parse_douyin_command(url)
    
    if result["success"]:
        return {
            "success": True,
            "product_id": result["product_id"],
            "title": result["title"],
            "price": result["price"],
            "detail_url": result["detail_url"]
        }
    else:
        return {
            "success": False,
            "error": result["error"]
        }