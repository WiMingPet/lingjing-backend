"""
商家工作台服务
"""
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from app.models.task import Task
from app.config import settings


class MerchantService:

    @staticmethod
    def generate_size_table(height_cm: int, weight_kg: int) -> Dict:
        """
        根据身高体重查标准尺码表，返回各尺码的胸围、腰围、臀围参考值
        参考中国服装号型标准 GB/T 1335
        """
        # 标准尺码对照表（女装常用）
        # 格式：身高范围, 体重范围, 推荐尺码, 胸围, 腰围, 臀围
        size_chart = [
            {"height": (150, 158), "weight": (40, 48), "size": "S", "bust": 80, "waist": 62, "hip": 86},
            {"height": (155, 163), "weight": (48, 55), "size": "M", "bust": 84, "waist": 66, "hip": 90},
            {"height": (160, 168), "weight": (55, 63), "size": "L", "bust": 88, "waist": 70, "hip": 94},
            {"height": (165, 173), "weight": (63, 72), "size": "XL", "bust": 92, "waist": 74, "hip": 98},
            {"height": (170, 180), "weight": (72, 82), "size": "XXL", "bust": 96, "waist": 78, "hip": 102},
        ]

        # 找匹配的尺码
        recommended = None
        for item in size_chart:
            h_min, h_max = item["height"]
            w_min, w_max = item["weight"]
            if h_min <= height_cm <= h_max and w_min <= weight_kg <= w_max:
                recommended = item
                break

        # 找不到完全匹配时，按最近身高找
        if not recommended:
            closest = min(size_chart, key=lambda x: abs((x["height"][0] + x["height"][1]) / 2 - height_cm))
            recommended = closest

        # 生成完整尺码表
        result = {}
        for item in size_chart:
            result[item["size"]] = {
                "bust": item["bust"],
                "waist": item["waist"],
                "hip": item["hip"],
            }

        result["recommended_size"] = recommended["size"]

        return result

    @staticmethod
    def split_scene_texts(user_text: str, count: int) -> list:
        """
        把用户输入的卖点描述，拆分成 count 段营销文案。
        如果用户没输入，返回空字符串列表（表示纯场景图）
        """
        import requests
        import json
        import re

        if not user_text or not user_text.strip():
            return [""] * count

        try:
            prompt = f"""你是电商详情页设计专家。用户输入了一段商品描述：
"{user_text}"

请把它拆分成 {count} 段营销文案，每段用于一张场景图。
要求：
1. 前几张侧重核心卖点、细节、材质、场景等不同角度
2. 最后几张可以留空，表示纯场景图不添加文字
3. 每段文案不超过15个字，简洁有力，适合图片内展示
4. 只返回JSON数组，格式：["文案1","文案2",""]，不要输出其他内容
"""
            resp = requests.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "qwen3.7-plus",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 500,
                },
                timeout=30,
            )
            content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"[DEBUG] 文案拆分原始返回: {content}")

            match = re.search(r"\[.*\]", content, re.DOTALL)
            if match:
                arr = json.loads(match.group(0))
                while len(arr) < count:
                    arr.append("")
                return arr[:count]
            else:
                return [""] * count
        except Exception as e:
            print(f"[DEBUG] 文案拆分失败，使用原始输入: {e}")
            arr = [""] * count
            arr[0] = user_text
            return arr