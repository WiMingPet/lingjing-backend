import os
import json
import time
import asyncio
import tempfile
import logging
import requests
from typing import List, Optional
from crawl4ai import AsyncWebCrawler
from crawl4ai.extraction_strategy import LLMExtractionStrategy
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from moviepy import VideoFileClip, concatenate_videoclips

from app.schemas.ecommerce import ProductInfo, CopywritingScript
from app.services.kling import KlingService

from crawl4ai import AsyncWebCrawler, LLMConfig
from crawl4ai.extraction_strategy import LLMExtractionStrategy

logger = logging.getLogger(__name__)

# 定义商品数据的结构，帮助AI准确提取
class ProductSchema(BaseModel):
    product_name: str = Field(..., description="商品名称")
    price: str = Field(..., description="商品价格")
    description: str = Field(..., description="商品详细描述")
    image_urls: List[str] = Field(..., description="商品图片URL列表")


class EcommerceService:
    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://hnd1.aihub.zeabur.ai/v1")
        self.crawl4ai_key = os.environ.get("CRAWL4AI_API_KEY")  # 可选，Crawl4AI 可能不需要
        self.kling = KlingService()

    async def parse_product_url(self, url: str) -> ProductInfo:
        """解析商品链接（带反检测）"""
        try:
            async with AsyncWebCrawler(
                headless=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                ignore_robots_txt=True,
                stealth=True
            ) as crawler:
                extraction_strategy = LLMExtractionStrategy(
                    llm_config=LLMConfig(provider="openai/gpt-4o-mini", api_token=self.api_key),
                    schema=ProductSchema.model_json_schema(),
                    instruction="从当前网页中提取商品名称、价格、描述和所有图片链接。"
                )
            
                result = await crawler.arun(
                    url=url,
                    extraction_strategy=extraction_strategy,
                    bypass_cache=True,
                )
            
                if result.success:
                    extracted_data = json.loads(result.extracted_content)
                    product_data = extracted_data[0]
                    return ProductInfo(
                        title=product_data.get("product_name", ""),
                        price=product_data.get("price", ""),
                        description=product_data.get("description", ""),
                        images=product_data.get("image_urls", []),
                        platform=self._detect_platform(url)
                    )
                else:
                    logger.warning(f"解析失败: {result.error_message}")
                    return self._get_mock_product_info(url)
        except Exception as e:
            logger.error(f"爬虫异常: {e}")
            return self._get_mock_product_info(url)
    def _detect_platform(self, url: str) -> str:
        if "taobao.com" in url or "tmall.com" in url:
            return "taobao"
        elif "jd.com" in url:
            return "jd"
        elif "douyin.com" in url:
            return "douyin"
        return "unknown"

    def _get_mock_product_info(self, url: str) -> ProductInfo:
        import re
        platform = self._detect_platform(url)
        product_id = re.search(r'(\d+)', url)
        title = f"商品_{product_id.group(1)}" if product_id else "测试商品"
        return ProductInfo(
            title=title,
            price="99.00",
            description="这是一个测试商品的描述",
            images=[],
            platform=platform
        )

    async def generate_product_demo_video(self, product: ProductInfo) -> Optional[str]:
        """生成商品展示视频"""
        if not product.images:
            return None
    
        product_image_url = product.images[0]
        prompt = f"展示商品{product.title}，从多个角度展示，突出卖点，自然光线，4K高清。"
    
        task_id = await self.kling.generate_video(
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
        client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        
        # 设计详细的提示词
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
        
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        
        content = response.choices[0].message.content
        result = json.loads(content)
        
        return CopywritingScript(
            title=result.get("title", "AI带货视频"),
            script=result.get("script", ""),
            scenes=result.get("scenes", [])
        )

    async def create_product_video(self, script: CopywritingScript, product: ProductInfo, digital_human_id: Optional[int] = None) -> dict:
        # 1. 生成数字人讲解视频
        digital_task_id = await self.kling.generate_digital_human(
            digital_human_id=digital_human_id,
            text=script.script,
        )
        digital_video_url = await self._wait_for_video(digital_task_id)
    
        # 2. 生成商品展示视频（单个）
        product_video_url = await self.generate_product_demo_video(product)
    
        # 3. 合并视频（转为列表传入）
        product_video_urls = [product_video_url] if product_video_url else []
        final_video_url = await self._merge_videos(digital_video_url, product_video_urls)
    
        return {
            "task_id": digital_task_id,
            "video_url": final_video_url,
            "status": "completed"
        }

    async def _wait_for_video(self, task_id: str, max_wait: int = 300) -> str:
        """轮询等待视频生成完成"""
        start_time = time.time()
        while time.time() - start_time < max_wait:
            status = await self.kling.get_video_task_status(task_id)
            if status.get("task_status") == "succeed":
                return status.get("task_result", {}).get("video_url")
            elif status.get("task_status") == "failed":
                raise Exception(f"视频生成失败: {status.get('task_status_msg')}")
            await asyncio.sleep(5)
        raise Exception("视频生成超时")

    async def _wait_for_videos(self, task_ids: List[str]) -> List[str]:
        """等待多个视频生成完成"""
        urls = []
        for task_id in task_ids:
            url = await self._wait_for_video(task_id)
            urls.append(url)
        return urls

    async def _merge_videos(self, digital_video_url: str, product_video_urls: List[str]) -> str:
        """使用moviepy将数字人视频和商品展示视频合并"""
        clips = []
        
        # 下载数字人视频
        digital_response = requests.get(digital_video_url)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_digital:
            tmp_digital.write(digital_response.content)
            digital_clip = VideoFileClip(tmp_digital.name)
            clips.append(digital_clip)
        
        # 下载并添加商品展示视频片段
        for url in product_video_urls:
            response = requests.get(url)
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_prod:
                tmp_prod.write(response.content)
                prod_clip = VideoFileClip(tmp_prod.name)
                clips.append(prod_clip)
        
        # 合并所有片段
        final_clip = concatenate_videoclips(clips)
        
        # 保存合成视频到临时文件
        output_path = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
        final_clip.write_videofile(output_path, fps=24)
        
        # 上传到OSS并返回URL（这里需要调用你的OSS上传服务）
        # from app.utils.file_utils import upload_file_helper
        # file_url, _ = await upload_file_helper(output_path, "ecommerce_videos")
        # return file_url
        
        # 临时返回本地路径（实际使用时替换为OSS URL）
        return output_path