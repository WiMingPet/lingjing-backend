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
from moviepy.editor import VideoFileClip, concatenate_videoclips

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
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://hnd1.aihub.zeabur.ai/v1")
        self.crawl4ai_key = os.environ.get("CRAWL4AI_API_KEY")  # 可选，Crawl4AI 可能不需要
        self.kling = KlingService()

    async def parse_product_url(self, url: str) -> ProductInfo:
        """
        使用Crawl4AI + LLM解析商品链接，提取结构化信息
        """
        async with AsyncWebCrawler(api_key=self.crawl4ai_key) as crawler:
            # 设置LLM提取策略
            extraction_strategy = LLMExtractionStrategy(
                provider="openai/gpt-4o-mini",
                api_token=self.api_key,
                schema=ProductSchema.model_json_schema(),
                instruction="从当前网页中提取商品名称、价格、描述和所有图片链接。"
            )
            
            result = await crawler.arun(
                url=url,
                extraction_strategy=extraction_strategy,
                bypass_cache=True,
            )
            
            if not result.success:
                raise Exception(f"商品解析失败: {result.error_message}")
            
            extracted_data = json.loads(result.extracted_content)
            product_data = extracted_data[0]  # 取第一个结果
            
            # 解析出所属平台（简单实现）
            platform = "unknown"
            if "taobao.com" in url or "tmall.com" in url:
                platform = "taobao"
            elif "jd.com" in url:
                platform = "jd"
            elif "douyin.com" in url:
                platform = "douyin"
            
            return ProductInfo(
                title=product_data.get("product_name", ""),
                price=product_data.get("price", ""),
                description=product_data.get("description", ""),
                images=product_data.get("image_urls", []),
                platform=platform
            )

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

    async def create_product_video(self, script: CopywritingScript, digital_human_id: Optional[int] = None) -> dict:
        """
        根据脚本生成最终带货视频
        返回: {"task_id": "...", "video_url": "...", "status": "processing|completed|failed"}
        """
        # 1. 生成数字人主播视频
        digital_task_id = await self.kling.generate_digital_human(
            digital_human_id=digital_human_id,
            text=script.script,
        )
        
        # 2. 等待数字人视频完成
        digital_video_url = await self._wait_for_video(digital_task_id)
        
        # 3. 生成商品展示视频（使用可灵图生视频）
        product_video_urls = []
        # 如果有商品图片，可以生成展示视频（这里简化处理，实际可以更复杂）
        # for scene in script.scenes:
        #     task_id = await self.kling.generate_video(prompt=scene)
        #     url = await self._wait_for_video(task_id)
        #     product_video_urls.append(url)
        
        # 4. 合并视频
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