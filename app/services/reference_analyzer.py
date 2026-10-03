"""
参考图分析服务：用 qwen-vl-max 识别参考图里的角色信息
"""
import json
import re
import asyncio
import requests
from typing import List, Dict
from app.config import settings


class ReferenceAnalyzer:

    @staticmethod
    async def analyze(image_urls: List[str]) -> List[Dict]:
        """
        分析多张参考图，返回每张图的角色信息
        返回：[{"reference_index": 1, "gender": "female", "age_range": "mid 20s", "appearance": "..."}]
        """
        results = []
        for i, url in enumerate(image_urls):
            info = await ReferenceAnalyzer._analyze_one(url, i + 1)
            results.append(info)
        return results

    @staticmethod
    async def _analyze_one(image_url: str, index: int) -> Dict:
        """分析单张参考图"""
        prompt = """分析这张图里的人物，输出严格 JSON 格式：
{
  "gender": "male 或 female",
  "age_range": "如 early 20s / mid 20s / early 30s / mid 30s / 40s",
  "appearance": "英文描述，20-30 词，包含人种、发型、服装、显著特征"
}

要求：
- gender 必须是 "male" 或 "female"
- age_range 用英文，如 "mid 20s"
- appearance 用英文，描述人物的外貌特征，方便后续生成相似角色
- 只输出 JSON，不要任何解释、不要 markdown 代码块"""

        def _sync():
            resp = requests.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "qwen-vl-max",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": image_url}},
                                {"type": "text", "text": prompt},
                            ],
                        }
                    ],
                    "temperature": 0.3,
                },
                timeout=60,
            )
            if resp.status_code != 200:
                raise Exception(f"qwen-vl 错误: {resp.status_code} {resp.text[:200]}")
            text = resp.json()["choices"][0]["message"]["content"]
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                return json.loads(match.group(0))
            raise Exception("无法解析参考图分析结果")

        try:
            info = await asyncio.to_thread(_sync)
            info["reference_index"] = index
            info["image_url"] = image_url
            print(f"[REF_ANALYZER] 图 {index}: {info}")
            return info
        except Exception as e:
            print(f"[REF_ANALYZER] 图 {index} 分析失败: {e}")
            return {
                "reference_index": index,
                "image_url": image_url,
                "gender": "unknown",
                "age_range": "unknown",
                "appearance": "",
            }


reference_analyzer = ReferenceAnalyzer()