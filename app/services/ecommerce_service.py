import os
import json
import time
import asyncio
import tempfile
import logging
import requests
import re
from typing import List, Optional, Tuple
from urllib.parse import unquote
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.schemas.ecommerce import ProductInfo, CopywritingScript
from app.services.kling import KlingService
from app.services.oss_service import oss_service
from app.data.preset_avatars import PRESET_AVATARS  # 【新增】导入预设形象

logger = logging.getLogger(__name__)


class ProductSchema(BaseModel):
    product_name: str = Field(..., description="商品名称")
    price: str = Field(..., description="商品价格")
    description: str = Field(..., description="商品详细描述")
    image_urls: List[str] = Field(..., description="商品图片URL列表")


class EcommerceService:
    def __init__(self):
        self.api_key = "sk-xS3B_2aEVaLpvM7zAju_xA"
        self.base_url = "https://hnd1.aihub.zeabur.ai/v1"
        self.kling = KlingService()

    # ==================== 【修复2】自动选择预设形象 ====================
    def _select_avatar_for_product(self, product_title: str, product_type: str = "") -> dict:
        """
        根据商品标题自动选择最合适的数字人形象
        规则：
        - 女装/女性相关 → 选择露西(美妆带货) 或 美娜(女教师)
        - 男装/男性相关 → 选择宇航(成熟男性) 或 燃锋(潮流男生)
        - 默认 → 露西(最通用的带货形象)
        """
        title_lower = product_title.lower()
        
        # 女性商品关键词
        female_keywords = ["女", "裙", "连衣裙", "女装", "女士", "妈妈", "女性", "美妆", "护肤", "化妆", 
                          "高跟鞋", "丝袜", "内衣", "文胸", "bra", "口红", "粉底", "眼影"]
        # 男性商品关键词
        male_keywords = ["男", "男装", "男士", "爸爸", "男性", "西装", "领带", "皮鞋", "剃须", "皮带"]
        
        is_female = any(kw in title_lower for kw in female_keywords)
        is_male = any(kw in title_lower for kw in male_keywords)
        
        if is_male and not is_female:
            # 选男性形象：优先燃锋(年轻潮流)，备选宇航(成熟稳重)
            for avatar in PRESET_AVATARS:
                if avatar["id"] == 5:  # 燃锋
                    print(f"[DEBUG] 自动选择男性形象: {avatar['name']}")
                    return avatar
        elif is_female or "裤" in title_lower or "衣" in title_lower or "服装" in title_lower:
            # 选女性带货形象：优先露西(美妆带货)，备选美娜
            for avatar in PRESET_AVATARS:
                if avatar["id"] == 12:  # 露西
                    print(f"[DEBUG] 自动选择女性带货形象: {avatar['name']}")
                    return avatar
        
        # 默认：露西
        for avatar in PRESET_AVATARS:
            if avatar["id"] == 12:
                print(f"[DEBUG] 使用默认带货形象: {avatar['name']}")
                return avatar
        
        return PRESET_AVATARS[0]  # 兜底

    # ==================== 本地解析抖音链接 ====================
    def _parse_douyin_from_url(self, url: str) -> Optional[dict]:
        """从抖音分享链接的 URL 参数中直接提取商品信息"""
        final_url = url
        
        if "v.douyin.com" in url:
            try:
                response = requests.get(url, allow_redirects=True, timeout=10)
                final_url = response.url
                print(f"[DEBUG] 短链接重定向后: {final_url}")
            except Exception as e:
                print(f"[DEBUG] 短链接重定向失败: {e}")
                return None
        
        # 从 goods_detail 参数提取
        match = re.search(r'goods_detail=([^&]+)', final_url)
        if match:
            encoded_json = match.group(1)
            decoded_json = unquote(encoded_json)
            try:
                goods_detail = json.loads(decoded_json)
                price_fen = goods_detail.get("min_price", 0)
                img_data = goods_detail.get("img", {})
                images = img_data.get("url_list", [])
                
                title = goods_detail.get("title", "")
                
                # ========== 新增：提取视频 URL ==========
                video_url = None
                video_data = goods_detail.get("video", {})
                if video_data.get("url_list"):
                    video_url = video_data["url_list"][0]
                if not video_url:
                    from urllib.parse import unquote
                    video_match = re.search(r'video_url=([^&]+)', unquote(final_url))
                    if video_match:
                        video_url = unquote(video_match.group(1))
                # ========== 提取结束 ==========
                
                print(f"[DEBUG] 本地解析成功: {title[:50]}...")
                print(f"[DEBUG] 获取到 {len(images)} 张图片")
                if video_url:
                    print(f"[DEBUG] 获取到视频: {video_url[:80]}...")
                
                return {
                    "title": title,
                    "price": price_fen / 100 if price_fen else 0,
                    "description": title,
                    "images": images,
                    "video_url": video_url
                }
            except Exception as e:
                print(f"[DEBUG] goods_detail 解析异常: {e}")
        
        # 备选：从 title 参数提取
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
        
        return None

    async def parse_product_url(self, url: str) -> ProductInfo:
        """解析商品链接"""
        import httpx
        import os
        
        # 优先本地解析
        local_result = self._parse_douyin_from_url(url)
        if local_result and local_result.get("title"):
            print(f"[INFO] 本地解析成功: {local_result['title']}")
            return ProductInfo(
                title=local_result["title"],
                price=str(local_result["price"]),
                description=local_result["description"],
                images=local_result.get("images", []),
                video_url=local_result.get("video_url"),
                platform="douyin"
            )
        
        # 订单侠兜底
        print("[INFO] 本地解析失败，尝试订单侠...")
        apikey = os.environ.get("DINGDANXIA_APIKEY")
        if not apikey:
            raise Exception("未配置订单侠API Key，且本地解析失败")
        
        api_url = "https://api.tbk.dingdanxia.com/douyin/shareCommandParse"
        payload = {"apikey": apikey, "command": url}
        
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                response = await client.post(api_url, json=payload, headers={"Content-Type": "application/json"})
                try:
                    data = response.json()
                except:
                    raise Exception("订单侠返回数据格式错误")
                
                if data.get("code") == 0:
                    result = data.get("data", {})
                    price_fen = result.get("price", 0)
                    return ProductInfo(
                        title=result.get("title", ""),
                        price=str(price_fen / 100 if price_fen else 0),
                        description=result.get("title", ""),
                        images=[],
                        platform="douyin"
                    )
                else:
                    raise Exception(f"订单侠解析失败: {data.get('msg', '未知错误')}")
        except Exception as e:
            raise Exception(f"所有解析方式均失败: {str(e)}")

    def _extract_douyin_id(self, url: str) -> str:
        """从抖音链接中提取商品ID"""
        if "v.douyin.com" in url:
            try:
                response = requests.get(url, allow_redirects=True, timeout=10)
                url = response.url
            except:
                pass
        
        patterns = [r'product/(\d+)', r'goods/(\d+)', r'item_id=(\d+)', r'(\d{19})']
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
        """用商品图片生成展示视频"""
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

    async def generate_copywriting(self, product: ProductInfo, is_manual_mode: bool = False) -> CopywritingScript:
        """调用 OpenAI 生成带货口播文案"""
        client = AsyncOpenAI(
            api_key=self.api_key, 
            base_url=self.base_url,
            timeout=60.0
        )
    
        if is_manual_mode:
            # 【核心】先让 AI 识别产品图片
            if product.images:
                detected_name, detected_desc = await self._analyze_product_image(
                    product.images[0], 
                    user_input=product.description
                )
                # 用识别结果覆盖
                product.title = detected_name or product.title
                product.description = detected_desc or product.description
            
            prompt = f"""
你是一位顶级的直播带货主播，需要根据以下产品信息，生成一段约60秒的直播口播文案。

产品信息：
- 名称：{product.title}
- 详细描述：{product.description}

创作要求：
1. 风格：真实、有感染力、有购买号召力，像真人在直播间的即兴发挥。
2. 结构：开场抓眼球（2秒内） -> 产品卖点介绍（材质、款式、解决什么痛点） -> 适合什么样的人群 -> 使用场景 -> 促销引导。
3. 文案必须严格基于以上产品信息，不能编造。
4. 输出格式为JSON：
   {{
     "title": "抓眼球的视频标题",
     "script": "完整的口播文案（约300字，保证能讲满60秒）"
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
            if not content:
                raise Exception("AI返回内容为空")
        
            result = json.loads(content)
            return CopywritingScript(
                title=result.get("title", "AI带货视频"),
                script=result.get("script", ""),
                scenes=result.get("scenes", [])
            )
        except Exception as e:
            print(f"AI生成失败 (重试一次): {e}")
            try:
                response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=500,
                    temperature=0.8
                )
                content = response.choices[0].message.content
                result = json.loads(content)
                return CopywritingScript(
                    title=result.get("title", "AI带货视频"),
                    script=result.get("script", ""),
                    scenes=result.get("scenes", [])
                )
            except Exception as e2:
                print(f"AI重试也失败: {e2}")
                raise Exception(f"AI文案生成失败，请稍后重试")

    # ==================== 【修复1+2+3+4】完整的视频生成主流程 ====================
    async def create_product_video(
        self, 
        script: CopywritingScript, 
        product: ProductInfo, 
        digital_image_url: str = None, 
        digital_human_id: Optional[int] = None,
        user_token: str = None,  # 【新增】用户token，用于调用试穿接口
        is_manual_mode: bool = False  # ✅ 保留
    ) -> dict:
        """生成完整带货视频"""
        
        # 【修复2】自动选择预设形象
        avatar = self._select_avatar_for_product(product.title)
        digital_human_image = digital_image_url or avatar.get("model_image", "")
        print(f"[DEBUG] 使用数字人形象: {avatar['name']} - {digital_human_image}")
        
        # 1. 生成数字人讲解视频
        print(f"[DEBUG] 开始生成数字人讲解视频...")
        digital_task_id = await self.kling.generate_digital_human(
            digital_human_id=digital_human_id,
            text=script.script,
            image_url=digital_human_image
        )
        digital_video_url = await self._wait_for_video(digital_task_id)
        print(f"[DEBUG] 数字人视频生成完成")
        
        # 2. 生成商品展示视频
        product_video_url = None
        product_images = product.images or []
        
        fashion_keywords = [
            "裤", "衣", "裙", "服装", "T恤", "衬衫", "外套", "卫衣",
            "短袖", "长袖", "夹克", "羽绒", "马甲", "背心", "毛衣",
            "针织", "风衣", "大衣", "棉服", "西服", "套装", "连体"
        ]
        is_fashion = any(keyword in product.title for keyword in fashion_keywords)
        
        # 情况1：链接里有视频 → 直接用原视频
        if hasattr(product, 'video_url') and product.video_url:
            product_video_url = product.video_url
            print(f"[DEBUG] 使用链接内视频: {product_video_url}")
        
        # 情况2：手动模式 + 服装类 → 虚拟试穿
        elif is_manual_mode and is_fashion and product_images:
            print(f"[DEBUG] 手动模式+服装类：调用虚拟试穿...")
            product_video_url = await self._call_tryon_api(
                garment_image_url=product_images[0],
                model_image_url=digital_human_image,
                user_token=user_token
            )
            if not product_video_url:
                print(f"[DEBUG] 试穿失败，降级为原图展示...")
                product_video_url = await self._image_to_video(product_images[0], duration=5)
        
        # 情况3：链接模式 + 服装类 → 虚拟试穿
        elif not is_manual_mode and is_fashion and product_images:
            print(f"[DEBUG] 链接模式+服装类：调用虚拟试穿...")
            product_video_url = await self._call_tryon_api(
                garment_image_url=product_images[0],
                model_image_url=digital_human_image,
                user_token=user_token
            )
            if not product_video_url:
                print(f"[DEBUG] 试穿失败，降级为原图展示...")
                product_video_url = await self._image_to_video(product_images[0], duration=5)
        
        # 情况4：非服装类（无论手动还是链接）→ 原图展示
        elif product_images:
            print(f"[DEBUG] 非服装类商品，用原图生成展示视频...")
            product_video_url = await self._image_to_video(product_images[0], duration=5)
        
        # 3. 合并视频
        if product_video_url:
            final_video_url = await self._merge_videos(digital_video_url, [product_video_url])
        else:
            final_video_url = digital_video_url
        
        print(f"[DEBUG] 带货视频生成完成")
        return {
            "task_id": digital_task_id,
            "video_url": final_video_url,
            "status": "completed"
        }

    # ==================== 【修复1】正确调用虚拟试穿接口 ====================
    async def _call_tryon_api(self, garment_image_url: str, model_image_url: str, user_token: str = None) -> Optional[str]:
        """
        通过URL调用虚拟试穿接口（内部新接口，无需下载图片）
        """
        import aiohttp
        import os
        
        try:
            print(f"[DEBUG] 通过URL调用试穿接口（无需下载图片）")
            print(f"[DEBUG] 服装图: {garment_image_url[:80]}...")
            print(f"[DEBUG] 模特图: {model_image_url[:80]}...")
            
            timeout = aiohttp.ClientTimeout(total=120)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                api_url = "https://lingjing.preview.aliyun-zeabur.cn/api/tryon/generate_by_url"
                
                payload = {
                    "model_image_url": model_image_url,
                    "garment_image_url": garment_image_url
                }
                
                headers = {
                    "Content-Type": "application/json",
                    "X-Internal-Key": os.getenv("INTERNAL_API_KEY", "lingjing-internal-2026")
                }
                if user_token:
                    headers["Authorization"] = f"Bearer {user_token}"
                
                print(f"[DEBUG] 调用试穿URL接口: {api_url}")
                
                async with session.post(api_url, json=payload, headers=headers) as resp:
                    print(f"[DEBUG] 试穿API响应状态: {resp.status}")
                    if resp.status == 200:
                        result = await resp.json()
                        task_data = result.get("data", {})
                        task_id = task_data.get("id")
                        if task_id:
                            video_url = await self._wait_for_tryon_result(task_id, user_token)
                            if video_url:
                                print(f"[DEBUG] 虚拟试穿视频已生成")
                                return video_url
                    else:
                        response_text = await resp.text()
                        print(f"[DEBUG] 试穿API返回: {resp.status} - {response_text[:200]}")
                        
        except aiohttp.client_exceptions.ClientError as e:
            print(f"[DEBUG] 试穿网络请求失败: {e}")
        except Exception as e:
            print(f"[DEBUG] 虚拟试穿异常: {e}")
        
        return None

    async def _wait_for_tryon_result(self, task_id: int, user_token: str = None, max_wait: int = 300) -> Optional[str]:
        """轮询等待试穿任务完成"""
        import aiohttp
        
        start_time = time.time()
        poll_count = 0
        api_url = f"https://lingjing.preview.aliyun-zeabur.cn/api/tryon/task/{task_id}"
        headers = {}
        if user_token:
            headers["Authorization"] = f"Bearer {user_token}"
        
        while time.time() - start_time < max_wait:
            poll_count += 1
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_url, headers=headers) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            data = result.get("data", {})
                            status = data.get("status", "")
                            output_data = data.get("output_data", {})
                            video_url = output_data.get("video_url", "")
                            
                            print(f"[DEBUG] 试穿任务状态(轮询{poll_count}): {status}")
                            
                            if status == "completed" and video_url:
                                return video_url
                            elif status == "failed":
                                return None
            except Exception as e:
                print(f"[DEBUG] 查询试穿状态异常: {e}")
            
            interval = 5 if poll_count <= 10 else 10
            await asyncio.sleep(interval)
        
        print(f"[DEBUG] 试穿任务超时")
        return None

    # ==================== 【修复4】优化轮询间隔 ====================
    async def _wait_for_video(self, task_id: str, max_wait: int = 600) -> str:
        """
        轮询等待视频生成完成
        动态间隔：前10次5秒，之后10秒
        总超时600秒（10分钟）
        """
        start_time = time.time()
        poll_count = 0
        print(f"[DEBUG] 开始轮询视频任务: {task_id}")
        while time.time() - start_time < max_wait:
            poll_count += 1
            try:
                status = self.kling.get_digital_human_task_status(task_id)
                task_status = status.get("task_status")
                print(f"[DEBUG] 第{poll_count}次轮询，状态: {task_status}")
                
                if task_status == "succeed":
                    task_result = status.get("task_result", {})
                    videos = task_result.get("videos", [])
                    if videos:
                        video_url = videos[0].get("url")
                    else:
                        video_url = task_result.get("video_url")
                    print(f"[DEBUG] 视频生成成功，共轮询{poll_count}次")
                    return video_url
                elif task_status == "failed":
                    error_msg = status.get("task_status_msg", "未知错误")
                    raise Exception(f"视频生成失败: {error_msg}")
            except Exception as e:
                if "失败" in str(e):
                    raise
                print(f"[DEBUG] 查询状态异常: {e}")
            
            interval = 5 if poll_count <= 10 else 10
            await asyncio.sleep(interval)
        
        raise Exception(f"视频生成超时，共轮询{poll_count}次")

    async def _wait_for_videos(self, task_ids: List[str]) -> List[str]:
        urls = []
        for task_id in task_ids:
            url = await self._wait_for_video(task_id)
            urls.append(url)
        return urls
    async def _analyze_product_image(self, image_url: str, user_input: str = "") -> Tuple[str, str]:
        """
        分析图片，返回 (product_name, detailed_description)
        """
        import aiohttp
        
        try:
            # 下载图片并转为 base64
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    image_data = await resp.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            # 调用 OpenAI 视觉模型
            client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=60.0
            )
            
            prompt = f"""
请仔细分析这张产品图片，提取以下信息：
1. 产品名称（具体到款式、类型）
2. 核心卖点（至少3个）
3. 材质/面料
4. 适合人群（年龄、性别、风格偏好）
5. 适用场景（至少2个）
6. 如果有{user_input}，请结合用户输入的内容

输出格式严格为JSON：
{{
  "product_name": "具体产品名称",
  "selling_points": "核心卖点，用中文逗号分隔",
  "description": "一段约100字的详细产品描述，包含材质、版型、风格"
}}
"""
            
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }],
                max_tokens=500,
                temperature=0.5
            )
            
            content = response.choices[0].message.content
            result = json.loads(content)
            return result.get("product_name", "商品"), result.get("description", "")
            
        except Exception as e:
            print(f"图片识别失败: {e}")
            return "优质商品", "质量保证，性价比高"

    async def _merge_videos(self, digital_video_url: str, product_video_urls: List[str]) -> str:
        """使用 ffmpeg 合并视频"""
        import subprocess
        import aiohttp
        
        files_to_clean = []
        
        try:
            video_files = []
            urls = [digital_video_url] + product_video_urls
            
            async with aiohttp.ClientSession() as session:
                for url in urls:
                    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
                    async with session.get(url) as resp:
                        tmp.write(await resp.read())
                    tmp.close()
                    video_files.append(tmp.name)
                    files_to_clean.append(tmp.name)
            
            list_file = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w")
            for vf in video_files:
                list_file.write(f"file '{vf}'\n")
            list_file.close()
            files_to_clean.append(list_file.name)
            
            output_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            output_file.close()
            files_to_clean.append(output_file.name)
            
            cmd = [
                "ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file.name,
                "-c", "copy", output_file.name, "-y"
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
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