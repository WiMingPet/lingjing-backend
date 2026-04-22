import os
import json
import time
import aiofiles
import asyncio
import tempfile
import logging
import requests
from typing import List, Optional
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from moviepy import VideoFileClip, concatenate_videoclips

from app.schemas.ecommerce import ProductInfo, CopywritingScript
from app.services.kling import KlingService

logger = logging.getLogger(__name__)

# 定义商品数据的结构，帮助AI准确提取
class ProductSchema(BaseModel):
    product_name: str = Field(..., description="商品名称")
    price: str = Field(..., description="商品价格")
    description: str = Field(..., description="商品详细描述")
    image_urls: List[str] = Field(..., description="商品图片URL列表")


class EcommerceService:
    def __init__(self):
        # 直接写入你的 API Key（不要从环境变量读取）
        self.api_key = "sk-effTartCqXaPPp_ccIcJ3g"
        self.base_url = "https://hnd1.aihub.zeabur.ai/v1"
        self.kling = KlingService()

    # ========== 本地解析抖音链接（不需要订单侠） ==========
    def _parse_douyin_from_url(self, url: str) -> dict:
        """从抖音分享链接的 URL 参数中直接提取商品信息"""
        import re
        from urllib.parse import unquote
        import json
        import requests as sync_requests
        
        final_url = url
        
        # 处理短链接
        if "v.douyin.com" in url:
            try:
                response = sync_requests.get(url, allow_redirects=True, timeout=10)
                final_url = response.url
                print(f"[DEBUG] 短链接重定向后: {final_url}")
            except Exception as e:
                print(f"[DEBUG] 短链接重定向失败: {e}")
                return None
        
        # 提取 goods_detail 参数
        match = re.search(r'goods_detail=([^&]+)', final_url)
        if not match:
            print("[DEBUG] 未找到 goods_detail 参数")
            return None
        
        encoded_json = match.group(1)
        decoded_json = unquote(encoded_json)
        
        try:
            goods_detail = json.loads(decoded_json)
            price_fen = goods_detail.get("min_price", 0)
            
            # 提取图片 URL
            img_data = goods_detail.get("img", {})
            images = img_data.get("url_list", [])
            
            print(f"[DEBUG] 本地解析成功: {goods_detail.get('title', '')[:50]}...")
            print(f"[DEBUG] 获取到 {len(images)} 张图片")
            
            return {
                "title": goods_detail.get("title", ""),
                "price": price_fen / 100 if price_fen else 0,
                "description": goods_detail.get("title", ""),
                "images": images  # 返回图片数组
            }
        except Exception as e:
            print(f"[DEBUG] 本地解析异常: {e}")
            return None

    async def parse_product_url(self, url: str) -> ProductInfo:
        """
        解析商品链接，获取商品信息
        优先使用本地解析（从 URL 参数提取），失败后再尝试订单侠
        """
        import httpx
        import os
        
        # ========== 优先使用本地解析 ==========
        local_result = self._parse_douyin_from_url(url)
        if local_result and local_result.get("title"):
            print(f"[INFO] 本地解析成功: {local_result['title']}")
            return ProductInfo(
                title=local_result["title"],
                price=str(local_result["price"]),
                description=local_result["description"],
                images=local_result.get("images", []),  # 使用解析到的图片
                platform="douyin"
            )
        
        # ========== 本地解析失败，尝试订单侠 ==========
        print("[INFO] 本地解析失败，尝试订单侠...")
        
        apikey = os.environ.get("DINGDANXIA_APIKEY")
        if not apikey:
            raise Exception("未配置订单侠API Key，且本地解析失败")
        
        # 订单侠配置（使用 IP 直连）
        orderxia_ip = os.environ.get("DINGDANXIA_IP", "61.160.192.99")
        orderxia_host = os.environ.get("DINGDANXIA_HOST", "api.tbk.dingdanxia.com")
        api_path = "/douyin/shareCommandParse"
        api_url = f"http://{orderxia_ip}{api_path}"
        
        headers = {
            "Host": orderxia_host,
            "Content-Type": "application/json",
        }
        
        payload = {
            "apikey": apikey,
            "command": url
        }
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(api_url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                if data.get("code") == 0:
                    result = data.get("data", {})
                    price_fen = result.get("price", 0)
                    return ProductInfo(
                        title=result.get("title", ""),
                        price=str(price_fen / 100 if price_fen else 0),
                        description=result.get("title", ""),
                        images=[],  # 订单侠不返回图片
                        platform="douyin"
                    )
                else:
                    error_msg = data.get("msg", "未知错误")
                    raise Exception(f"订单侠解析失败: {error_msg}")
        except Exception as e:
            raise Exception(f"所有解析方式均失败: {str(e)}")

    def _extract_douyin_id(self, url: str) -> str:
        """从抖音链接中提取商品 ID（保留备用）"""
        import re
        import requests
        
        # 如果是短链接，先获取重定向后的真实 URL
        if "v.douyin.com" in url:
            try:
                response = requests.get(url, allow_redirects=True, timeout=10)
                url = response.url
                print(f"[DEBUG] 短链接重定向后: {url}")
            except Exception as e:
                print(f"[DEBUG] 短链接重定向失败: {e}")
        
        patterns = [
            r'product/(\d+)',
            r'goods/(\d+)',
            r'item_id=(\d+)',
            r'(\d{19})'
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _detect_platform(self, url: str) -> str:
        if "taobao.com" in url or "tmall.com" in url:
            return "taobao"
        elif "jd.com" in url:
            return "jd"
        elif "douyin.com" in url:
            return "douyin"
        return "unknown"

    # ⚠️ 删除 _get_mock_product_info 方法，不再生成模拟数据

    async def generate_product_demo_video(self, product: ProductInfo) -> Optional[str]:
        if not product.images:
            return None

        product_image_url = product.images[0]
        prompt = f"展示商品{product.title}，从多个角度展示，突出卖点，自然光线，4K高清。"

        task_id = self.kling.generate_video(  # ✅ 去掉 await
            image_url=product_image_url,
            prompt=prompt,
            duration=5,
            mode="std"
        )
        video_url = await self._wait_for_video(task_id)
        return video_url

    async def generate_copywriting(self, product: ProductInfo) -> CopywritingScript:
        """
        调用OpenAI生成带货口播文案和分镜描述
        """
        client = AsyncOpenAI(
            api_key=self.api_key, 
            base_url=self.base_url,
            timeout=60.0
        )
    
        prompt = f"""
    你是一位顶级的直播带货主播，请根据以下商品信息，生成一段约60秒的口播文案和分镜描述。

    商品信息：
    - 标题：{product.title}
    - 价格：{product.price}
    - 描述：{product.description}

    要求：
    1. 口播文案需有吸引力，包含开场、产品介绍、痛点解决、促销引导。
    2. 分镜描述需指明每一段文案对应的画面建议（如：特写商品、展示使用场景、数字人主播正面镜头等）。
    3. 输出格式为JSON：
       {{
         "title": "视频标题",
         "script": "完整口播文案",
         "scenes": ["分镜1描述", "分镜2描述", ...]
       }}
    """
    
        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.7
            )
        
            content = response.choices[0].message.content
            print(f"AI返回内容: {content}")
        
            if not content:
                raise Exception("AI返回内容为空")
        
            result = json.loads(content)
        
            return CopywritingScript(
                title=result.get("title", "AI带货视频"),
                script=result.get("script", ""),
                scenes=result.get("scenes", [])
            )
        except Exception as e:
            print(f"AI生成失败: {e}")
            # 返回默认文案（但使用真实商品信息）
            return CopywritingScript(
                title="AI带货视频",
                script=f"家人们！今天给大家推荐这款{product.title}，只要{product.price}元，赶快下单吧！",
                scenes=["开场", "展示", "结束"]
            )

    async def create_product_video(self, script: CopywritingScript, product: ProductInfo, digital_image_url: str = None, digital_human_id: Optional[int] = None) -> dict:
        """生成完整带货视频"""
    
        # 使用默认数字人照片
        digital_human_image = digital_image_url
        if not digital_human_image:
            # 使用你昨天上传的图片 URL
            digital_human_image = "https://media.lingjing-media.com/Scr.jpg"
    
        # 1. 生成数字人讲解视频
        digital_task_id = await self.kling.generate_digital_human(
            digital_human_id=digital_human_id,
            text=script.script,
            image_url=digital_human_image
        )
    
        digital_video_url = await self._wait_for_video(digital_task_id)
        
        # 2. 生成商品展示视频（如果有商品图片）
        product_video_url = await self.generate_product_demo_video(product)
        
        # 3. 合并视频
        if product_video_url:
            final_video_url = await self._merge_videos(digital_video_url, [product_video_url])
        else:
            final_video_url = digital_video_url
        
        return {
            "task_id": digital_task_id,
            "video_url": final_video_url,
            "status": "completed"
        }

    async def _wait_for_video(self, task_id: str, max_wait: int = 300) -> str:
        """轮询等待视频生成完成"""
        start_time = time.time()
        print(f"[DEBUG] 开始轮询视频任务: {task_id}")
        while time.time() - start_time < max_wait:
            try:
                status = self.kling.get_digital_human_task_status(task_id)
                task_status = status.get("task_status")
                print(f"[DEBUG] 数字人任务状态: {task_status}")
                
                if task_status == "succeed":
                    task_result = status.get("task_result", {})
                    # 可灵 API 返回的视频 URL 在 videos 数组中
                    videos = task_result.get("videos", [])
                    if videos:
                        video_url = videos[0].get("url")
                    else:
                        video_url = task_result.get("video_url")
                    print(f"[DEBUG] 视频生成成功: {video_url}")
                    return video_url
                elif task_status == "failed":
                    error_msg = status.get("task_status_msg", "未知错误")
                    raise Exception(f"视频生成失败: {error_msg}")
            except Exception as e:
                print(f"[DEBUG] 查询状态异常: {e}")
            
            await asyncio.sleep(5)
        
        raise Exception(f"视频生成超时，task_id: {task_id}")

    async def _wait_for_videos(self, task_ids: List[str]) -> List[str]:
        """等待多个视频生成完成"""
        urls = []
        for task_id in task_ids:
            url = await self._wait_for_video(task_id)
            urls.append(url)
        return urls

    async def _merge_videos(self, digital_video_url: str, product_video_urls: List[str]) -> str:
        """使用moviepy将数字人视频和商品展示视频合并"""
        from app.utils.file_utils import upload_file_helper
        
        clips = []
        temp_files = []
        
        try:
            # 1. 下载数字人视频
            digital_response = requests.get(digital_video_url)
            digital_response.raise_for_status()
            
            digital_temp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            digital_temp.write(digital_response.content)
            digital_temp.flush()
            digital_temp.close()
            temp_files.append(digital_temp.name)
            
            digital_clip = VideoFileClip(digital_temp.name)
            clips.append(digital_clip)
            
            # 2. 下载商品展示视频
            for url in product_video_urls:
                response = requests.get(url)
                response.raise_for_status()
                
                prod_temp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
                prod_temp.write(response.content)
                prod_temp.flush()
                prod_temp.close()
                temp_files.append(prod_temp.name)
                
                prod_clip = VideoFileClip(prod_temp.name)
                clips.append(prod_clip)
            
            # 3. 合并视频
            if len(clips) == 1:
                final_clip = clips[0]
            else:
                final_clip = concatenate_videoclips(clips, method="compose")
            
            # 4. 保存合并后的视频
            output_path = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
            temp_files.append(output_path)
            
            final_clip.write_videofile(
                output_path,
                fps=24,
                codec='libx264',
                audio_codec='aac',
                threads=2,
                logger=None
            )
            
            # 5. 上传到 OSS（使用 aiofiles 流式读取）
            async with aiofiles.open(output_path, 'rb') as f:
                file_url, _ = await upload_file_helper(f, "ecommerce_videos")
            
            return file_url
            
        except Exception as e:
            print(f"[ERROR] 视频合并失败: {e}")
            import traceback
            traceback.print_exc()
            raise
            
        finally:
            # 6. 关闭所有剪辑
            for clip in clips:
                try:
                    clip.close()
                except:
                    pass
            try:
                final_clip.close()
            except:
                pass
            
            # 7. 清理临时文件
            for file_path in temp_files:
                try:
                    if os.path.exists(file_path):
                        os.unlink(file_path)
                except:
                    pass