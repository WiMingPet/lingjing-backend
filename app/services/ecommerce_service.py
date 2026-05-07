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
from app.data.preset_avatars import PRESET_AVATARS

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

    def _select_avatar_for_product(self, product_title: str) -> dict:
        title_lower = product_title.lower()
        if any(kw in title_lower for kw in ["男", "男装", "数码", "汽车"]):
            for avatar in PRESET_AVATARS:
                if avatar["id"] == 5:
                    return avatar
        if any(kw in title_lower for kw in ["美妆", "护肤", "化妆"]):
            for avatar in PRESET_AVATARS:
                if avatar["id"] == 12:
                    return avatar
        if any(kw in title_lower for kw in ["儿童", "教育", "老师"]):
            for avatar in PRESET_AVATARS:
                if avatar["id"] == 10:
                    return avatar
        for avatar in PRESET_AVATARS:
            if avatar["id"] == 12:
                return avatar
        return PRESET_AVATARS[0]

    def _ai_select_avatar(self, product_title: str, product_description: str) -> dict:
        avatar_options = []
        for avatar in PRESET_AVATARS:
            avatar_options.append(f"ID:{avatar['id']}, 姓名:{avatar['name']}, 类别:{avatar['category']}, 描述:{avatar['description']}")
        avatar_list_str = "\n".join(avatar_options)
        
        prompt = f"""
你是一位顶尖的直播带货策划师。请根据以下产品信息，从形象列表中选出最合适的带货数字人形象。

产品标题：{product_title}
产品描述：{product_description}

形象列表：
{avatar_list_str}

选择标准：
1. 形象的气质、年龄、性别必须与产品的目标受众和风格完全匹配。
2. 例如，美妆产品首选"露西"(ID:12)，男装或数码产品首选"燃锋"(ID:5)或"宇航"(ID:7)，知识付费首选"文慧"(ID:1)或"明悦"(ID:6)。
3. 请只返回选中形象的 ID 数字，不要包含其他任何内容。
"""
        try:
            import requests as sync_requests
            
            response = sync_requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 10,
                    "temperature": 0.3
                },
                timeout=30
            )
            result = response.json()
            raw_response = result["choices"][0]["message"]["content"].strip()
            import re
            digits = re.findall(r'\d+', raw_response)
            if digits:
                avatar_id = int(digits[0])
            else:
                raise Exception(f"无法解析AI返回: {raw_response}")
            for avatar in PRESET_AVATARS:
                if avatar["id"] == avatar_id:
                    print(f"[AI决策] 选中形象: {avatar['name']} (ID:{avatar_id})")
                    return avatar
        except Exception as e:
            print(f"[AI决策] 失败，降级为关键词规则: {e}")
        
        return self._select_avatar_for_product(product_title)

    def _ai_select_voice(self, product_title: str, product_description: str, avatar: dict) -> str:
        voice_options = [
            {"name": "温柔女声", "desc": "温暖柔和，适合女性产品、情感类"},
            {"name": "播报男声", "desc": "沉稳专业，适合男性产品、商务类"},
            {"name": "钓系女友", "desc": "活泼俏皮，适合美妆、年轻时尚产品"},
            {"name": "自然男声", "desc": "磁性有魅力，适合高端产品、男性受众"},
            {"name": "知性女声", "desc": "知性优雅，适合知识科普、文艺产品"},
        ]
        voice_list_str = "\n".join([f"- {v['name']}: {v['desc']}" for v in voice_options])
        
        prompt = f"""
请根据以下信息，从音色列表中选择最合适的音色。

产品标题：{product_title}
产品描述：{product_description}
已选形象：{avatar['name']}（{avatar['description']}）

音色列表：
{voice_list_str}

要求：只返回音色名称，不要包含其他内容。例如：温柔女声
"""
        try:
            import requests as sync_requests
            
            response = sync_requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 10,
                    "temperature": 0.3
                },
                timeout=30
            )
            result = response.json()
            voice_name = result["choices"][0]["message"]["content"].strip()
            print(f"[AI决策] 选中音色: {voice_name}")
            return voice_name
        except Exception as e:
            print(f"[AI决策] 音色选择失败，使用默认值: {e}")
        
        if avatar["id"] in [5, 7]:
            return "播报男声"
        return "温柔女声"

    def _parse_douyin_from_url(self, url: str) -> Optional[dict]:
        final_url = url
        
        if "v.douyin.com" in url:
            try:
                response = requests.get(url, allow_redirects=True, timeout=10)
                final_url = response.url
                print(f"[DEBUG] 短链接重定向后: {final_url}")
            except Exception as e:
                print(f"[DEBUG] 短链接重定向失败: {e}")
                return None
        
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
                
                video_url = None
                video_data = goods_detail.get("video", {})
                if video_data.get("url_list"):
                    video_url = video_data["url_list"][0]
                if not video_url:
                    video_match = re.search(r'video_url=([^&]+)', unquote(final_url))
                    if video_match:
                        video_url = unquote(video_match.group(1))
                
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
        import httpx
        import os
        
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
        client = AsyncOpenAI(
            api_key=self.api_key, 
            base_url=self.base_url,
            timeout=60.0
        )
    
        if is_manual_mode:
            if product.images:
                detected_name, detected_desc = await self._analyze_product_image(
                    product.images[0], 
                    user_input=product.description
                )
                product.title = detected_name or product.title
                product.description = detected_desc or product.description
            
            prompt = f"""
你是一个顶级的直播带货主播，正在镜头前给粉丝们推荐一款产品。请你像真人一样生动地讲解，语气要有感染力、互动感、号召力，多用"家人们"、"宝宝们"、"咱们"这类口语，自然地展示产品卖点和优点。

产品：{product.title}
卖点：{product.description or '高品质，性价比超高'}

输出严格JSON格式：{{"script": "完整的口播文案（约300字，适合60秒讲解）"}}
"""
        else:
            prompt = f"""
你是一位顶级的直播带货主播，请根据以下商品信息，生成一段约60秒的口播文案和分镜描述。

商品信息：
- 标题：{product.title}
- 价格：{product.price}
- 描述：{product.description}

要求：
1. 口播文案需有吸引力，包含开场、产品介绍、痛点解决、促销引导。
2. 分镜描述需指明每一段文案对应的画面建议。
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

    async def create_product_video(
        self, 
        script: CopywritingScript, 
        product: ProductInfo, 
        digital_image_url: str = None, 
        digital_human_id: Optional[int] = None,
        user_token: str = None,
        is_manual_mode: bool = False
    ) -> dict:
        """生成完整带货视频"""
        
        avatar = self._ai_select_avatar(product.title, product.description or "")
        digital_human_image = digital_image_url or avatar.get("model_image", "")
        print(f"[DEBUG] 使用数字人形象: {avatar['name']} - {digital_human_image}")
        
        voice_name = self._ai_select_voice(product.title, product.description or "", avatar)
        print(f"[DEBUG] 使用音色: {voice_name}")
        
        # 第一步：生成商品展示视频
        product_video_url = None
        tryon_image_url = None
        product_images = product.images or []
        
        fashion_keywords = [
            "裤", "衣", "裙", "服装", "T恤", "衬衫", "外套", "卫衣",
            "短袖", "长袖", "夹克", "羽绒", "马甲", "背心", "毛衣",
            "针织", "风衣", "大衣", "棉服", "西服", "套装", "连体"
        ]
        is_fashion = any(keyword in product.title for keyword in fashion_keywords)
        
        if hasattr(product, 'video_url') and product.video_url:
            product_video_url = product.video_url
            print(f"[DEBUG] 使用链接内视频: {product_video_url}")
        elif is_manual_mode and is_fashion and product_images:
            print(f"[DEBUG] 手动模式+服装类：调用虚拟试穿...")
            product_video_url, tryon_image_url = await self._call_tryon_api(
                garment_image_url=product_images[0],
                model_image_url=digital_human_image,
                user_token=user_token
            )
            if not product_video_url:
                print(f"[DEBUG] 试穿失败，降级为原图展示...")
                product_video_url = await self._image_to_video(product_images[0], duration=5)
        elif not is_manual_mode and is_fashion and product_images:
            print(f"[DEBUG] 链接模式+服装类：调用虚拟试穿...")
            product_video_url, tryon_image_url = await self._call_tryon_api(
                garment_image_url=product_images[0],
                model_image_url=digital_human_image,
                user_token=user_token
            )
            if not product_video_url:
                print(f"[DEBUG] 试穿失败，降级为原图展示...")
                product_video_url = await self._image_to_video(product_images[0], duration=5)
        elif product_images:
            print(f"[DEBUG] 非服装类商品，用原图生成展示视频...")
            product_video_url = await self._image_to_video(product_images[0], duration=5)

        # 第二步：使用数字人API生成与文案同步的讲解视频
        print(f"[DEBUG] 开始生成数字人口播视频...")
        from app.services.tts_service import get_voice_type
        
        # 关键：使用试穿效果图作为数字人形象，而非原始预设形象
        digital_human_image = tryon_image_url if tryon_image_url else digital_human_image
        print(f"[DEBUG] 数字人形象使用: {'试穿效果图' if tryon_image_url else '预设形象'}")
        
        # 将脚本中的 voice_name 正确地传递给API
        digital_task_id = await self.kling.generate_digital_human(
            digital_human_id=digital_human_id,
            text=script.script,
            image_url=digital_human_image,
            voice=voice_name
        )
        digital_video_url = await self._wait_for_video(digital_task_id)
        print(f"[DEBUG] 数字人口播视频生成完成")
        
        # 第三步：合并视频。如果数字人生成失败，降级为将TTS音频合入试穿视频
        if digital_video_url:
            if product_video_url:
                final_video_url = await self._merge_videos(digital_video_url, [product_video_url])
            else:
                final_video_url = digital_video_url
        elif product_video_url:
            # 降级方案
            print("[DEBUG] 数字人生成失败，使用TTS音频降级方案")
            from app.services.tts_service import tts_service
            voice_type = get_voice_type(voice_name) if voice_name else 101001
            audio_bytes = tts_service.text_to_speech(script.script, voice_type)
            audio_url = await oss_service.upload_file(audio_bytes, "mp3", "ecommerce_audio")
            final_video_url = await self._merge_audio_only(product_video_url, audio_url)
        else:
            final_video_url = None
        
        print(f"[DEBUG] 带货视频生成完成")
        return {
            "video_url": final_video_url,
            "status": "completed"
        }

    async def _image_to_video(self, image_url: str, duration: int = 5) -> str:
        """把图片转成固定时长的视频"""
        import subprocess
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    image_data = await resp.read()
            
            tmp_image = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            tmp_image.write(image_data)
            tmp_image.close()
            
            tmp_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            tmp_video.close()
            
            cmd = [
                "ffmpeg", "-loop", "1", "-i", tmp_image.name,
                "-c:v", "libx264", "-t", str(duration),
                "-pix_fmt", "yuv420p", "-y",
                tmp_video.name
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            with open(tmp_video.name, "rb") as f:
                result_url = await oss_service.upload_file(f.read(), "mp4", "product_images")
            
            os.unlink(tmp_image.name)
            os.unlink(tmp_video.name)
            
            return result_url
            
        except Exception as e:
            print(f"[ERROR] 图片转视频失败: {e}")
            return None

    async def _call_tryon_api(self, garment_image_url: str, model_image_url: str, user_token: str = None):
        from app.services.tryon_service import TryonService
        from app.database import SessionLocal
        
        try:
            print(f"[DEBUG] 直接调用试穿服务（与手动试穿相同流程）")
            print(f"[DEBUG] 服装图: {garment_image_url[:80]}...")
            print(f"[DEBUG] 模特图: {model_image_url[:80]}...")
            
            request_data = {
                "model_image_url": model_image_url,
                "garment_image_url": garment_image_url
            }
            
            db = SessionLocal()
            try:
                task = await TryonService.generate_tryon(db, 1, request_data)
                
                if task.output_data:
                    video_url = task.output_data.get("video_url", "")
                    if video_url:
                        print(f"[DEBUG] 虚拟试穿视频已生成: {video_url[:80]}...")
                        tryon_image_url = task.output_data.get("tryon_image_url", "")
                        return video_url, tryon_image_url
            finally:
                db.close()
            
            print(f"[DEBUG] 试穿任务未获取到视频URL")
            return None
            
        except Exception as e:
            print(f"[DEBUG] 虚拟试穿异常: {e}")
            import traceback
            traceback.print_exc()
            return None, None

    async def _wait_for_tryon_result(self, task_id: int, user_token: str = None, max_wait: int = 300) -> Optional[str]:
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

    async def _wait_for_video(self, task_id: str, max_wait: int = 1200) -> str:
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
        
        raise Exception(f"可灵平台高峰期排队中，视频生成超时（共轮询{poll_count}次），请稍后重试")

    async def _wait_for_videos(self, task_ids: List[str]) -> List[str]:
        urls = []
        for task_id in task_ids:
            url = await self._wait_for_video(task_id)
            urls.append(url)
        return urls
        
    async def _analyze_product_image(self, image_url: str, user_input: str = "") -> Tuple[str, str]:
        import aiohttp
        import base64
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    image_data = await resp.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            import requests as sync_requests
            
            prompt = """
请仔细分析这张产品图片，提取以下信息：
1. 产品名称（具体到款式、类型）
2. 核心卖点（至少3个）
3. 材质/面料
4. 适合人群（年龄、性别、风格偏好）
5. 适用场景（至少2个）

输出格式严格为JSON：
{
  "product_name": "具体产品名称",
  "selling_points": "核心卖点，用中文逗号分隔",
  "description": "一段约100字的详细产品描述，包含材质、版型、风格"
}
"""
            
            response = sync_requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                            ]
                        }
                    ],
                    "max_tokens": 500,
                    "temperature": 0.5
                },
                timeout=60
            )
            
            result = response.json()
            print(f"[DEBUG] 图片识别响应: {result}")
            
            choices = result.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                if content:
                    clean_content = content.strip()
                    if clean_content.startswith('```'):
                        clean_content = clean_content.split('\n', 1)[-1]
                        if clean_content.endswith('```'):
                            clean_content = clean_content[:-3]
                    parsed = json.loads(clean_content)
                    return parsed.get("product_name", "商品"), parsed.get("description", "")
            
            raise Exception(f"返回格式异常: {result}")
            
        except Exception as e:
            print(f"图片识别失败: {e}")
            return "时尚服装", "优质服装，版型好，面料舒适，性价比高"

    async def _merge_audio_only(self, video_url: str, audio_url: str) -> str:
        """将音频合成到试穿视频上，保留原画面，替换声音"""
        import subprocess
        import aiohttp
        
        files_to_clean = []
        try:
            async with aiohttp.ClientSession() as session:
                tmp_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
                async with session.get(video_url) as resp:
                    tmp_video.write(await resp.read())
                tmp_video.close()
                files_to_clean.append(tmp_video.name)
                
                tmp_audio = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                async with session.get(audio_url) as resp:
                    tmp_audio.write(await resp.read())
                tmp_audio.close()
                files_to_clean.append(tmp_audio.name)
            
            output_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            output_file.close()
            files_to_clean.append(output_file.name)
            
            cmd = [
                "ffmpeg", "-i", tmp_video.name, "-i", tmp_audio.name,
                "-c:v", "copy", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0",
                "-shortest", "-y", output_file.name
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            with open(output_file.name, "rb") as f:
                return await oss_service.upload_file(f.read(), "mp4", "ecommerce_videos")
        
        except Exception as e:
            print(f"[ERROR] 音频合并失败: {e}")
            return video_url
        
        finally:
            for file_path in files_to_clean:
                try:
                    if os.path.exists(file_path):
                        os.unlink(file_path)
                except:
                    pass

    async def _merge_audio_to_video(self, video_url: str, audio_video_url: str) -> str:
        import subprocess
        import aiohttp
        
        files_to_clean = []
        
        try:
            async with aiohttp.ClientSession() as session:
                tmp_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
                async with session.get(video_url) as resp:
                    tmp_video.write(await resp.read())
                tmp_video.close()
                files_to_clean.append(tmp_video.name)
                
                tmp_audio_source = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
                async with session.get(audio_video_url) as resp:
                    tmp_audio_source.write(await resp.read())
                tmp_audio_source.close()
                files_to_clean.append(tmp_audio_source.name)
            
            output_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            output_file.close()
            files_to_clean.append(output_file.name)
            
            cmd = [
                "ffmpeg", "-i", tmp_video.name, "-i", tmp_audio_source.name,
                "-c:v", "copy", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0",
                "-y", output_file.name
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            with open(output_file.name, "rb") as f:
                return await oss_service.upload_file(f.read(), "mp4", "ecommerce_videos")
        
        except Exception as e:
            print(f"[ERROR] 音频合并失败: {e}")
            return video_url
        
        finally:
            for file_path in files_to_clean:
                try:
                    if os.path.exists(file_path):
                        os.unlink(file_path)
                except:
                    pass

    async def _merge_videos(self, digital_video_url: str, product_video_urls: List[str]) -> str:
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