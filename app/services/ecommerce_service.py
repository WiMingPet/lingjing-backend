import os
import json
import time
import asyncio
import tempfile
import logging
import requests
import re
from typing import List, Optional
from urllib.parse import unquote
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.schemas.ecommerce import ProductInfo, CopywritingScript
from app.services.kling import KlingService
from app.services.oss_service import oss_service

logger = logging.getLogger(__name__)


class ProductSchema(BaseModel):
    product_name: str = Field(..., description="商品名称")
    price: str = Field(..., description="商品价格")
    description: str = Field(..., description="商品详细描述")
    image_urls: List[str] = Field(..., description="商品图片URL列表")


class EcommerceService:
    def __init__(self):
        # AI 文案生成配置
        self.api_key = "sk-effTartCqXaPPp_ccIcJ3g"
        self.base_url = "https://hnd1.aihub.zeabur.ai/v1"
        self.kling = KlingService()

    # ==================== 核心：本地解析抖音链接 ====================
    def _parse_douyin_from_url(self, url: str) -> Optional[dict]:
        """
        【强化】从抖音分享链接的 URL 参数中直接提取商品信息
        支持短链接重定向、goods_detail 和 title 参数提取
        """
        final_url = url
        
        # 1. 处理短链接重定向（同步执行，因为可能是同步函数调用）
        if "v.douyin.com" in url:
            try:
                response = requests.get(url, allow_redirects=True, timeout=10)
                final_url = response.url
                print(f"[DEBUG] 短链接重定向后: {final_url}")
            except Exception as e:
                print(f"[DEBUG] 短链接重定向失败: {e}")
                return None
        
        # 2. 优先从 goods_detail 参数提取（含商品标题、价格、图片）
        match = re.search(r'goods_detail=([^&]+)', final_url)
        if match:
            encoded_json = match.group(1)
            decoded_json = unquote(encoded_json)
            try:
                goods_detail = json.loads(decoded_json)
                price_fen = goods_detail.get("min_price", 0)
                img_data = goods_detail.get("img", {})
                images = img_data.get("url_list", [])
                
                # 修正图片 URL，获取高清大图
                fixed_images = []
                for img in images:
                    if "www800-800" in img:
                        fixed_images.append(img)
                    else:
                        fixed_images.append(img)
                
                title = goods_detail.get("title", "")
                print(f"[DEBUG] 本地解析成功: {title[:50]}...")
                print(f"[DEBUG] 获取到 {len(fixed_images)} 张图片")
                
                return {
                    "title": title,
                    "price": price_fen / 100 if price_fen else 0,
                    "description": title,  # 用标题作为初始描述
                    "images": fixed_images
                }
            except Exception as e:
                print(f"[DEBUG] goods_detail 解析异常: {e}")
        
        # 3. 备选：从 title 参数提取（兼容其他格式）
        decoded_url = unquote(final_url)
        title_match = re.search(r'title=([^&]+)', decoded_url)
        if title_match:
            try:
                title = unquote(title_match.group(1))
                print(f"[DEBUG] 从 title 参数提取: {title[:50]}...")
                return {
                    "title": title,
                    "price": "0",
                    "description": title,
                    "images": []
                }
            except:
                pass
        
        print("[DEBUG] 所有本地解析方式均未获取到有效信息")
        return None

    async def parse_product_url(self, url: str) -> ProductInfo:
        """
        【优化】解析商品链接，获取商品信息
        优先使用本地解析，失败后再尝试订单侠
        """
        import httpx
        import os
        
        # 一、优先使用本地解析
        local_result = self._parse_douyin_from_url(url)
        if local_result and local_result.get("title"):
            print(f"[INFO] 本地解析成功: {local_result['title']}")
            return ProductInfo(
                title=local_result["title"],
                price=str(local_result["price"]),
                description=local_result["description"],
                images=local_result.get("images", []),
                platform="douyin"
            )
        
        # 二、本地解析失败，尝试订单侠（改用 HTTPS + 域名）
        print("[INFO] 本地解析失败，尝试订单侠...")
        
        apikey = os.environ.get("DINGDANXIA_APIKEY")
        if not apikey:
            raise Exception("未配置订单侠API Key，且本地解析失败")
        
        api_url = "https://api.tbk.dingdanxia.com/douyin/shareCommandParse"
        
        payload = {
            "apikey": apikey,
            "command": url
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                response = await client.post(
                    api_url, 
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                print(f"[DEBUG] 订单侠响应状态码: {response.status_code}")
                
                try:
                    data = response.json()
                except Exception:
                    print(f"[DEBUG] 订单侠返回非JSON: {response.text[:500]}")
                    raise Exception("订单侠返回数据格式错误")
                
                if data.get("code") == 0:
                    result = data.get("data", {})
                    price_fen = result.get("price", 0)
                    print(f"[DEBUG] 订单侠解析成功: {result.get('title', '')[:50]}")
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
        import requests
        
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

    async def generate_product_demo_video(self, product: ProductInfo) -> Optional[str]:
        """保留：用商品图片生成展示视频（非服装类的降级方案）"""
        if not product.images:
            return None

        product_image_url = product.images[0]
        prompt = f"展示商品{product.title}，从多个角度展示，突出卖点，自然光线，4K高清。"

        task_id = self.kling.generate_video(
            image_url=product_image_url,
            prompt=prompt,
            duration=5,
            mode="std"
        )
        video_url = await self._wait_for_video(task_id)
        return video_url

    # ==================== AI 口播文案生成（保持不变） ====================
    async def generate_copywriting(self, product: ProductInfo) -> CopywritingScript:
        """
        调用 OpenAI 生成带货口播文案和分镜描述
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
            # 返回默认文案（使用真实商品信息）
            return CopywritingScript(
                title="AI带货视频",
                script=f"家人们！今天给大家推荐这款{product.title}，只要{product.price}元，这性价比简直太高了！赶快点击下方链接下单吧！",
                scenes=["开场", "展示", "结束"]
            )

    # ==================== 视频生成主流程（新增虚拟试穿逻辑） ====================
    async def create_product_video(
        self, 
        script: CopywritingScript, 
        product: ProductInfo, 
        digital_image_url: str = None, 
        digital_human_id: Optional[int] = None
    ) -> dict:
        """生成完整带货视频（数字人讲解 + 商品展示/试穿）"""
    
        # 使用默认数字人照片
        digital_human_image = digital_image_url
        if not digital_human_image:
            digital_human_image = "https://media.lingjing-media.com/Scr.jpg"
    
        # 1. 生成数字人讲解视频
        print(f"[DEBUG] 开始生成数字人讲解视频...")
        digital_task_id = await self.kling.generate_digital_human(
            digital_human_id=digital_human_id,
            text=script.script,
            image_url=digital_human_image
        )
        digital_video_url = await self._wait_for_video(digital_task_id)
        print(f"[DEBUG] 数字人视频生成完成: {digital_video_url}")
        
        # 2. 生成商品展示视频（带虚拟试穿逻辑）
        product_video_url = None
        
        if product.images:
            # 判断是否为服装类商品
            fashion_keywords = ["裤", "衣", "裙", "服装", "T恤", "衬衫", "外套", "卫衣", "短袖", "长袖", "夹克", "羽绒"]
            is_fashion = any(keyword in product.title for keyword in fashion_keywords)
            
            if is_fashion:
                print(f"[DEBUG] 检测到服装类商品，尝试调用虚拟试穿...")
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        tryon_response = await client.post(
                            "https://lingjing.preview.aliyun-zeabur.cn/api/tryon/generate",
                            json={
                                "person_image": digital_human_image,
                                "garment_image": product.images[0],
                                "category": "upper_body"
                            }
                        )
                        if tryon_response.status_code == 200:
                            tryon_result = tryon_response.json()
                            product_video_url = tryon_result.get("video_url")
                            print(f"[DEBUG] 虚拟试穿视频已生成: {product_video_url}")
                except Exception as e:
                    print(f"[DEBUG] 虚拟试穿失败，降级为图生视频: {e}")
            
            # 如果非服装类或试穿失败，使用图生视频降级方案
            if not product_video_url:
                print(f"[DEBUG] 使用图生视频生成商品展示...")
                product_video_url = await self.generate_product_demo_video(product)
        
        # 3. 合并视频
        if product_video_url:
            print(f"[DEBUG] 开始合并数字人视频和商品视频...")
            final_video_url = await self._merge_videos(digital_video_url, [product_video_url])
        else:
            final_video_url = digital_video_url
        
        print(f"[DEBUG] 带货视频生成完成: {final_video_url}")
        return {
            "task_id": digital_task_id,
            "video_url": final_video_url,
            "status": "completed"
        }

    # ==================== 辅助方法 ====================
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
        """【已替换为 ffmpeg】使用 ffmpeg 将数字人视频和商品展示视频合并"""
        import subprocess
        import aiohttp
        
        files_to_clean = []
        
        try:
            # 1. 下载所有视频
            video_files = []
            urls = [digital_video_url] + product_video_urls
            
            async with aiohttp.ClientSession() as session:
                for i, url in enumerate(urls):
                    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
                    async with session.get(url) as resp:
                        tmp.write(await resp.read())
                    tmp.close()
                    video_files.append(tmp.name)
                    files_to_clean.append(tmp.name)
            
            # 2. 创建 ffmpeg concat 文件列表
            list_file = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w")
            for vf in video_files:
                list_file.write(f"file '{vf}'\n")
            list_file.close()
            files_to_clean.append(list_file.name)
            
            # 3. ffmpeg 合并
            output_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            output_file.close()
            files_to_clean.append(output_file.name)
            
            cmd = [
                "ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file.name,
                "-c", "copy", output_file.name, "-y"
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # 4. 上传到 OSS
            with open(output_file.name, "rb") as f:
                return await oss_service.upload_file(f.read(), "mp4", "ecommerce_videos")
        
        except Exception as e:
            print(f"[ERROR] 视频合并失败: {e}")
            raise
        
        finally:
            for file_path in files_to_clean:
                try:
                    if os.path.exists(file_path):
                        os.unlink(file_path)
                except:
                    pass