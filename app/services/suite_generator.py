"""
套图生成服务 v8（AI 输出布局 JSON + 代码渲染）
"""
import asyncio
import requests
from io import BytesIO
from typing import Dict, List
from PIL import Image

from app.services.kling import kling_service
from app.services.image_composer import image_composer
from app.services.oss_service import oss_service
from app.services.matting_service import matting_service
from app.services.layout_renderer import layout_renderer
from app.config import settings


class SuiteGenerator:

    COMMON_NEGATIVE = (
        "**RULES: "
        "1) The product and the person (if any) MUST be offset: one on left, one on right; "
        "or one in foreground, one in background. "
        "2) The product MUST NOT overlap or cover the person's face, head, or body. "
        "3) The product's color, material, texture, shape MUST remain EXACTLY the same as the reference image. "
        "4) Real-life photography style, natural lighting, 4K HD, no text overlay. "
        "5) Environment fills 70%+ of frame. Product is small, part of the scene.**"
    )

    @staticmethod
    def _build_scene_prompt(analysis: Dict, scene_prompt: str) -> str:
        product_appearance = (analysis.get("product_appearance", "") or "")[:200]
        usage_analysis = (analysis.get("usage_analysis", "") or "")[:200]
        scene_prompt = (scene_prompt or "")[:400]

        prompt = (
            f"Scene: {scene_prompt}. "
            f"Product appearance: {product_appearance}. "
            f"Usage context: {usage_analysis}. "
            f"{SuiteGenerator.COMMON_NEGATIVE}"
        )

        if len(prompt) > 2400:
            prompt = prompt[:2400]
        return prompt

    # ==================== 白底图 ====================
    @staticmethod
    async def generate_white_bg(cloth_url: str) -> List[dict]:
        try:
            product_png = await matting_service.segment_commodity(cloth_url)
            if not product_png:
                return []

            def _compose():
                product = Image.open(BytesIO(product_png)).convert("RGBA")
                pw, ph = product.size
                cw, ch = int(pw * 1.4), int(ph * 1.4)
                canvas = Image.new("RGB", (cw, ch), (255, 255, 255))
                canvas.paste(product, ((cw - pw) // 2, (ch - ph) // 2), product)
                out = BytesIO()
                canvas.save(out, format="JPEG", quality=95)
                return out.getvalue()

            img_bytes = await asyncio.to_thread(_compose)
            if not img_bytes:
                return []

            clean_url = await oss_service.upload_file(
                img_bytes, "jpg", "merchant/white_bg_clean",
                bucket_name=settings.OSS_PRIVATE_BUCKET_NAME
            )
            watermarked = image_composer.add_ai_watermark(img_bytes)
            watermarked = image_composer.add_ai_metadata(watermarked)
            watermarked_url = await oss_service.upload_file(watermarked, "jpg", "merchant/white_bg")
            return [{"watermarked": watermarked_url, "clean": clean_url}]
        except Exception as e:
            print(f"[SUITE] 白底图生成失败: {e}")
            return []

    # ==================== 场景图（AI 自由布局）====================
    @staticmethod
    async def generate_scene_images(cloth_url: str, analysis: Dict, scene_count: int = 4) -> List[dict]:
        """
        场景图：按 AI 输出的布局 JSON 渲染
        - 数量由用户决定（scene_count）
        - 画布尺寸 1024x1024
        - 布局、场景、文案由 AI 自由决定
        - 可灵一定参考参考图（cloth_url）
        """
        return await SuiteGenerator._generate_aplus(cloth_url, analysis, scene_count, "scene")

    # ==================== A+ 生成（按 AI 布局 JSON）====================
    @staticmethod
    async def _generate_aplus(cloth_url: str, analysis: Dict, count: int, template_prefix: str) -> List[dict]:
        """
        按 AI 输出的布局 JSON 逐张渲染
        template_prefix 不再使用，仅保留兼容
        """
        canvas_size = analysis.get("canvas_size", [1464, 600])
        images_plan = analysis.get("images", [])

        if not images_plan:
            print("[SUITE-A+] AI 未输出 images 策划")
            return []

        global_o1_sem = asyncio.Semaphore(6)
        task_sem = asyncio.Semaphore(6)

        async def _gen_async(prompt_text, log_prefix):
            async with global_o1_sem:
                def _sync():
                    for attempt in range(2):   # ★ 最多重试 1 次
                        try:
                            task_id = kling_service.generate_image_o1(
                                prompt=prompt_text, image_urls=[cloth_url],
                                resolution="2k", aspect_ratio="1:1", n=1,
                            )
                            # ★ 超时从 600 改成 180
                            result = kling_service.wait_for_o1_result(task_id, max_wait=180)
                            url = result.get("output_url", "")
                            if url:
                                return url
                            print(f"[SUITE-A+] {log_prefix} 第 {attempt+1} 次无结果，重试")
                        except Exception as e:
                            print(f"[SUITE-A+] {log_prefix} 第 {attempt+1} 次失败: {e}")
                    return ""
                return await asyncio.to_thread(_sync)

        async def gen_one(plan: Dict):
            async with task_sem:
                index = plan.get("index", 1)
                elements = plan.get("elements", [])

                if not elements:
                    print(f"[SUITE-A+] 图 {index} 无 elements，跳过")
                    return None

                image_elements = [el for el in elements if el.get("type") == "image"]

                r = await asyncio.gather(*[
                    _gen_async(
                        SuiteGenerator._build_scene_prompt(analysis, el.get("scene_prompt", "")),
                        f"图{index}-{el.get('name', '')}"
                    )
                    for el in image_elements
                ], return_exceptions=True)

                image_urls = {}
                for k, el in enumerate(image_elements):
                    name = el.get("name", f"scene_{k}")
                    image_urls[name] = r[k] if k < len(r) and isinstance(r[k], str) else ""

                rendered = await layout_renderer.render_layout(canvas_size, elements, image_urls)

                if not rendered:
                    print(f"[SUITE-A+] 图 {index} 渲染失败")
                    return None

                clean_url = await oss_service.upload_file(
                    rendered, "jpg", "merchant/aplus_clean",
                    bucket_name=settings.OSS_PRIVATE_BUCKET_NAME
                )
                watermarked = image_composer.add_ai_watermark(rendered)
                watermarked = image_composer.add_ai_metadata(watermarked)
                watermarked_url = await oss_service.upload_file(
                    watermarked, "jpg", "merchant/aplus"
                )
                print(f"[SUITE-A+] ✅ 图 {index} 完成")
                return {"watermarked": watermarked_url, "clean": clean_url}

        raw = await asyncio.gather(*[gen_one(p) for p in images_plan[:count]])
        return [r for r in raw if r]

    @staticmethod
    async def generate_premium_aplus(cloth_url, analysis, count=6):
        return await SuiteGenerator._generate_aplus(cloth_url, analysis, count, "premium")

    @staticmethod
    async def generate_standard_aplus(cloth_url, analysis, count=6):
        return await SuiteGenerator._generate_aplus(cloth_url, analysis, count, "standard")

    @staticmethod
    async def generate_phone_aplus(cloth_url, analysis, count=6):
        return await SuiteGenerator._generate_aplus(cloth_url, analysis, count, "phone")


suite_generator = SuiteGenerator()