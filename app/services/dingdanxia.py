import httpx
import re
import os

async def get_douyin_product_info(url_or_code: str):
    """
    通过订单侠 API 获取抖音商品信息
    返回: { "title": "", "price": "", "image_url": "", "description": "" }
    """
    apikey = os.environ.get("DINGDANXIA_APIKEY")
    if not apikey:
        raise Exception("未配置 DINGDANXIA_APIKEY")
    
    # 1. 提取商品ID（如果是链接）
    product_id = extract_product_id(url_or_code)
    
    # 2. 调用订单侠商品详情接口
    api_url = "https://api.dingdanxia.com/douyin/goods/detail"
    
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            api_url,
            params={
                "apikey": apikey,
                "item_id": product_id,
                "platform": "douyin"
            }
        )
        data = response.json()
        
        if data.get("code") != 0:
            raise Exception(f"订单侠API错误: {data.get('msg')}")
        
        result = data.get("data", {})
        return {
            "title": result.get("title", ""),
            "price": result.get("price", ""),
            "image_url": result.get("image", ""),      # 商品主图
            "description": result.get("desc", "")
        }


def extract_product_id(url_or_code: str) -> str:
    """从抖音链接中提取商品ID"""
    # 常见抖音商品链接格式
    patterns = [
        r'product/(\d+)',
        r'goods/(\d+)',
        r'item_id=(\d+)',
        r'(\d{19})'  # 抖音商品ID通常是19位数字
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_code)
        if match:
            return match.group(1)
    return url_or_code  # 如果已经是纯ID，直接返回