"""
角色图生成服务
- 有参考图 → 用参考图生成定妆照
- 无参考图 → AI 生成
"""
import asyncio
from typing import Dict, Optional, List
from app.services.kling import kling_service


class CharacterGenerator:

    @staticmethod
    async def generate_character_image(
        character: Dict,
        style: str = "",
        reference_urls: List[str] = None
    ) -> Optional[str]:
        """生成单个角色的定妆照"""
        try:
            appearance = character.get("appearance", "")
            name = character.get("name", "")
            ref_idx = character.get("reference_index", 0)
            reference_urls = reference_urls or []

            # ★ 只保留画风维度（5 种）
            # real = 真人写实；anime_cn = 国漫 3D；anime_jp = 日漫 2D；anime_pixar = 皮克斯 3D；anime_us = 美漫 2D
            style_map = {
                "real": "photorealistic, cinematic portrait, 4K HD",
                "anime_cn": "Chinese 3D animation, donghua 3D, CGI character, cinematic lighting, highly detailed",
                "anime_jp": "Japanese anime style, 2D illustration, cel shading, clean line art, vibrant colors",
                "anime_pixar": "Pixar style, Disney 3D animation, CGI character, cute and stylized, cinematic lighting",
                "anime_us": "American comic style, 2D animation, bold outlines, vibrant colors, comic book illustration",
            }
            style_hint = style_map.get(style, "photorealistic, cinematic portrait, 4K HD")

            # ★ 有参考图
            ref_images = []
            if ref_idx and 1 <= ref_idx <= len(reference_urls):
                ref_images = [reference_urls[ref_idx - 1]]

            if ref_images:
                if style == "real" or not style:
                    vibe = character.get("vibe", "confident, modern, sophisticated")
                    outfit = character.get("outfit", "clean modern outfit, premium fabric")
                    prompt = (
                        f"Cinematic portrait of the person in the reference image. "
                        f"**The face, hair, skin tone, facial features MUST match the reference image exactly.** "
                        f"Keep the identity 100% consistent. "
                        f"Change the setting to: {outfit}, vibe: {vibe}. "
                        f"85mm portrait lens, shallow depth of field, "
                        f"soft cinematic side lighting, natural skin texture, "
                        f"professional editorial photography, magazine cover quality, "
                        f"half-body shot, looking at camera, confident expression. "
                        f"Clean neutral background, no text, no watermark."
                    )
                else:
                    prompt = (
                        f"Portrait of {appearance}, "
                        f"**the person's face, hair, skin tone MUST match the reference image exactly**, "
                        f"just change the setting to a neutral studio portrait, "
                        f"{style_hint}, beautiful face, refined features, no text"
                    )
            else:
                # ========== 真人写实：加气质/服装/模特脸/电影光 ==========
                if style == "real" or not style:
                    # 从 character 读气质和服装（script_generator 输出的）
                    vibe = character.get("vibe", "confident, modern, sophisticated")
                    outfit = character.get("outfit", "clean modern outfit, premium fabric")

                    prompt = (
                        f"Cinematic portrait of {appearance}. "
                        f"Vibe: {vibe}. "
                        f"Outfit: {outfit}. "
                        f"Fashion model face, high cheekbones, clear skin, symmetrical features, well-defined jawline. "
                        f"85mm portrait lens, shallow depth of field, bokeh background. "
                        f"Soft cinematic side lighting, natural skin texture, subtle rim light. "
                        f"Professional editorial photography, magazine cover quality, "
                        f"modern Chinese urban aesthetic, high-end commercial portrait. "
                        f"Half-body shot, looking at camera, confident expression. "
                        f"Clean neutral background, no text, no watermark, no logo."
                    )
                else:
                    # ========== 动漫/3D 风格：保持原逻辑，但加精致度 ==========
                    prompt = (
                        f"Portrait of {appearance}, "
                        f"{style_hint}, "
                        f"character reference sheet, front view, neutral background, "
                        f"highly detailed, beautiful face, refined features, "
                        f"professional character design, no text"
                    )

            def _sync():
                task_id = kling_service.generate_image_o1(
                    prompt=prompt,
                    image_urls=ref_images,
                    resolution="2k",      
                    aspect_ratio="1:1",
                    n=1,
                )
                result = kling_service.wait_for_o1_result(task_id, max_wait=300)  # ★ 时间也放宽
                return result.get("output_url", "")

            url = await asyncio.to_thread(_sync)
            print(f"[CHARACTER] {name} 生成成功（参考图 {ref_idx}）")
            return url
        except Exception as e:
            print(f"[CHARACTER] {character.get('name')} 失败: {e}")
            return None

    @staticmethod
    async def generate_all_characters(
        characters: list,
        style: str = "",
        reference_urls: List[str] = None
    ) -> Dict[str, str]:
        """
        生成"主角"的定妆照
        - 只生成 main（最多 3 个）
        - 有参考图 → 用参考图
        - 无参考图 → AI 生成
        """
        reference_urls = reference_urls or []

        # 所有角色都生成定妆照（main + supporting + extra）
        main_characters = characters
        if not main_characters:
            main_characters = characters[:3]

        print(f"[CHARACTER] 生成 {len(main_characters)} 个主角定妆照"
              f"（参考图 {len(reference_urls)} 张）")

        sem = asyncio.Semaphore(4)

        async def gen_one(character):
            async with sem:
                url = await CharacterGenerator.generate_character_image(
                    character, style, reference_urls
                )
                return (character["name"], url)

        results = await asyncio.gather(
            *[gen_one(c) for c in main_characters],
            return_exceptions=True
        )
        return {r[0]: r[1] for r in results if isinstance(r, tuple) and r[1]}


character_generator = CharacterGenerator()