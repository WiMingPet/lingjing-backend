"""
商品抠图服务 - Remove.bg
"""
import os
import requests
from typing import Optional


class MattingService:
    """商品抠图服务（Remove.bg）"""
    
    def __init__(self):
        self.api_key = os.getenv("REMOVE_BG_API_KEY", "")
        if not self.api_key:
            print("[MATTING] ⚠️ REMOVE_BG_API_KEY 未配置")
    
    async def segment_commodity(self, image_url: str) -> Optional[bytes]:
        """
        商品抠图
        - 输入：商品图 URL（任何来源）
        - 输出：透明背景的 PNG 字节流
        """
        if not self.api_key:
            print("[MATTING] ❌ 未配置 REMOVE_BG_API_KEY")
            return None
        
        try:
            print(f"[MATTING] 开始抠图: {image_url}")
            response = requests.post(
                "https://api.remove.bg/v1.0/removebg",
                data={
                    "image_url": image_url,
                    "size": "auto",
                    "format": "png",
                },
                headers={"X-Api-Key": self.api_key},
                timeout=60,
            )
            
            if response.status_code == 200:
                print(f"[MATTING] ✅ 抠图成功，大小: {len(response.content)} bytes")
                return response.content
            else:
                print(f"[MATTING] ❌ 抠图失败: {response.status_code}, {response.text[:200]}")
                return None
        
        except Exception as e:
            print(f"[MATTING] ❌ 异常: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def segment_common_image(self, image_url: str) -> Optional[bytes]:
        """兼容旧调用，直接调 segment_commodity"""
        return await self.segment_commodity(image_url)


matting_service = MattingService()