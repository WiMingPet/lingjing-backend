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
    ) -> Optional[str]:
        """生成分镜图（多人物 + 场景）"""
        try:
            # ★ 只保留画风维度
            # realistic = 真人写实；anime = 国产 3D 动画风
            style_map = {
                "realistic": "photorealistic, cinematic wide shot, 4K HD",
                "anime": "Chinese 3D animation, donghua 3D, CGI scene, cinematic wide shot, highly detailed",
            }
            style_hint = style_map.get(style, "photorealistic, cinematic wide shot, 4K HD")

            # 只取"有定妆照"的角色作参考
            reference_images = []
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

            prompt = (
                f"{scene_prompt}. "
                f"Characters in scene: {', '.join(characters_in_scene)}.{others_hint} "
                f"{style_hint}, "
                f"**characters with reference images MUST match the reference faces exactly**, "
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