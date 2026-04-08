"""
图片代理路由 - 解决防盗链问题
"""
import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import httpx

router = APIRouter(prefix="/proxy", tags=["代理"])


@router.get("/image")
async def proxy_image(url: str):
    """
    代理获取图片，绕过防盗链
    """
    try:
        # 设置请求头，模拟浏览器访问
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.klingai.com/",
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                return StreamingResponse(
                    response.iter_bytes(),
                    media_type=response.headers.get("content-type", "image/png"),
                    headers={"Content-Disposition": "inline"}
                )
            else:
                raise HTTPException(status_code=404, detail="图片获取失败")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))