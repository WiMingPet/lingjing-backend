"""
分镜图生成服务
"""
import asyncio
from typing import Dict, List, Optional
from app.services.kling import kling_service


class SceneGenerator:

    @staticmethod
    async def generate_scene_image(
        scene_prompt: str,
        character_images: Dict[str, str],
        characters_in_scene: List[str],
        style: str = "",
        prev_scene_image: str = None,   # ★ 新增
    ) -> Optional[str]:
        """生成分镜图（多人物 + 场景）"""
        try:
            # ★ 只保留画风维度（5 种）
            # real = 真人写实；anime_cn = 国漫 3D；anime_jp = 日漫 2D；anime_pixar = 皮克斯 3D；anime_us = 美漫 2D
            style_map = {
                "real": "photorealistic, cinematic wide shot, 4K HD",
                "anime_cn": "Chinese 3D animation, donghua 3D, CGI scene, cinematic wide shot, highly detailed",
                "anime_jp": "Japanese anime style, 2D illustration, cel shading, cinematic wide shot",
                "anime_pixar": "Pixar style, Disney 3D animation, CGI scene, cinematic wide shot",
                "anime_us": "American comic style, 2D animation, bold outlines, cinematic wide shot",
            }
            style_hint = style_map.get(style, "photorealistic, cinematic wide shot, 4K HD")

            # ★ 参考图：优先上一个分镜图，再加定妆照
            reference_images = []

            # 1. 上一个分镜图（放最前，权重最高）
            if prev_scene_image:
                reference_images.append(prev_scene_image)

            # 2. 角色定妆照
            for char_name in characters_in_scene:
                img = character_images.get(char_name)
                if img:
                    reference_images.append(img)

            reference_images = reference_images[:10]

            # "无定妆照"的角色，靠 prompt 描述
            unnamed = [c for c in characters_in_scene if c not in character_images]
            others_hint = ""
            if unnamed:
                others_hint = f" Also visible: {', '.join(unnamed)}."

            # ★ 连续性提示
            continuity_hint = ""
            if prev_scene_image:
                continuity_hint = (
                    "**CONTINUITY (HIGHEST PRIORITY)**: This scene MUST be a direct continuation of the previous scene. "
                    "Same location, same lighting, same time of day, same camera angle (or slight variation). "
                    "The characters must be in the exact same position they ended in the previous scene. "
                )

            prompt = (
                f"{scene_prompt}. "
                f"Characters in scene: {', '.join(characters_in_scene)}.{others_hint} "
                f"{style_hint}, "
                f"{continuity_hint}"
                f"**CRITICAL REFERENCE MATCHING (HIGHEST PRIORITY)**: "
                f"- Characters' faces MUST be EXACTLY the same as the reference images. "
                f"- Do NOT change age, gender, hairstyle, hair color, skin tone, eye shape, nose shape, mouth shape. "
                f"- Do NOT change clothing, accessories, or any visual detail. "
                f"all characters acting naturally, "
                f"highly detailed, no text, no subtitle"
            )

            def _sync():
                task_id = kling_service.generate_image_o1(
                    prompt=prompt,
                    image_urls=reference_images,
                    resolution="2k",
                    aspect_ratio="16:9",
                    n=1,
                )
                result = kling_service.wait_for_o1_result(task_id, max_wait=600)
                return result.get("output_url", "")

            return await asyncio.to_thread(_sync)
        except Exception as e:
            print(f"[SCENE] 分镜图失败: {e}")
            return None


scene_generator = SceneGenerator()