import os
import json
import time
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

    async def parse_product_url(self, url: str) -> ProductInfo:
        """
        使用订单侠 API 解析商品链接
        如果解析失败，直接抛出异常，不生成模拟数据
        """
        import httpx
        import re
        
        apikey = os.environ.get("DINGDANXIA_APIKEY")
        
        # ⚠️ 关键修改：如果没有配置 API Key，直接报错，不生成模拟数据
        if not apikey:
            logger.error("未配置 DINGDANXIA_APIKEY，无法解析链接")
            raise Exception("系统配置错误：未配置订单侠API Key")
        
        # 判断是否是抖音链接
        is_douyin = "douyin.com" in url or "iesdouyin.com" in url or "haohuo.jinritemai.com" in url or "v.douyin.com" in url
        
        if not is_douyin:
            # 非抖音链接，目前只支持抖音
            raise Exception(f"暂不支持该平台链接，目前仅支持抖音商品链接")
        
        # 解析抖音链接
        return await self._parse_douyin_url(url, apikey)

    async def _parse_douyin_url(self, url: str, apikey: str) -> ProductInfo:
        """
        使用订单侠解析抖音链接
        使用 IP 直连，绕过 DNS 解析问题
        """
        import httpx
        import re
        
        # 处理短链接，获取真实 URL
        final_url = url
        if "v.douyin.com" in url:
            try:
                import requests as sync_requests
                response = sync_requests.get(url, allow_redirects=True, timeout=10)
                final_url = response.url
                print(f"[DEBUG] 短链接重定向后: {final_url}")
            except Exception as e:
                print(f"[DEBUG] 短链接重定向失败: {e}")
        
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
            "command": final_url  # 使用重定向后的 URL
        }
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(api_url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                print(f"[DEBUG] 订单侠响应: {data}")
                
                # code=0 表示成功
                if data.get("code") == 0:
                    result = data.get("data", {})
                    price_fen = result.get("price", 0)
                    price_yuan = price_fen / 100 if price_fen else 0
                    
                    # ⚠️ 注意：订单侠不返回商品图片
                    # 返回 need_image 标记，让前端引导用户上传
                    return ProductInfo(
                        title=result.get("title", ""),
                        price=str(price_yuan),
                        description=result.get("title", ""),  # 用标题作为描述
                        images=[],  # 图片为空，需要用户上传
                        platform="douyin",
                        # 注意：ProductInfo 可能没有 need_image 字段，这里先返回空图片
                    )
                else:
                    error_msg = data.get("msg", "未知错误")
                    logger.error(f"订单侠解析失败: {error_msg}")
                    raise Exception(f"订单侠解析失败: {error_msg}")
                    
        except httpx.ConnectError as e:
            logger.error(f"订单侠连接失败: {e}")
            raise Exception("网络连接失败，请稍后重试")
        except httpx.TimeoutException:
            logger.error("订单侠请求超时")
            raise Exception("请求超时，请稍后重试")
        except Exception as e:
            logger.error(f"订单侠请求异常: {e}")
            raise Exception(f"解析失败: {str(e)}")

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
        if len(clips) == 1:
            final_clip = clips[0]
        else:
            final_clip = concatenate_videoclips(clips)
        
        # 保存合成视频到临时文件
        output_path = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
        final_clip.write_videofile(output_path, fps=24)
        
        # 关闭剪辑释放资源
        for clip in clips:
            clip.close()
        final_clip.close()
        
        # 上传到 OSS
        file_url, _ = await upload_file_helper(output_path, "ecommerce_videos")
        
        # 清理临时文件
        os.unlink(output_path)
        
        return file_url