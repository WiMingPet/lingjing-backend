"""
商品分析服务：AI 输出布局规格 JSON，彻底不硬编码
"""
import json
import re
import requests
from typing import Dict
from app.config import settings


# ==================== 套图类型规格（平台硬性要求）====================
SUITE_TYPE_SPECS = {
    "premium_aplus": {
        "name": "高级 A+",
        "canvas_size": [1464, 600],
        "image_count": 6,
        "style": "high-end, minimalist, premium feel, generous whitespace, luxury",
        "layout_preference": "large product images, clean typography, luxury feel, 1-4 images per canvas",
        "min_images_per_canvas": 1,
        "max_images_per_canvas": 4,
    },
    "standard_aplus": {
        "name": "标准 A+",
        "canvas_size": [970, 600],
        "image_count": 6,
        "style": "standard, product-focused, feature-driven, clear",
        "layout_preference": "product image + text, clear features, 1-4 images per canvas",
        "min_images_per_canvas": 1,
        "max_images_per_canvas": 4,
    },
    "phone_aplus": {
        "name": "手机 A+",
        "canvas_size": [600, 450],
        "image_count": 6,
        "style": "mobile-first, compact, vertical-friendly, punchy",
        "layout_preference": "single image + short text, mobile optimized, 1-2 images per canvas",
        "min_images_per_canvas": 1,
        "max_images_per_canvas": 2,
    },
    "scene": {
        "name": "场景图",
        "canvas_size": [1024, 1024],
        "image_count": None,          # None = 用户决定
        "style": "lifestyle, real scene, product in context, natural",
        "layout_preference": "AI 自由决定布局：可以全屏图、可以多宫格、可以带文字、可以不带文字",
        "min_images_per_canvas": 1,
        "max_images_per_canvas": 4,
        "allow_text": True,
    },
    "white_bg": {
        "name": "白底图",
        "canvas_size": [1024, 1024],
        "image_count": 1,
        "style": "clean white background, product only, professional",
        "layout_preference": "product centered, no text, 1 image per canvas",
        "min_images_per_canvas": 1,
        "max_images_per_canvas": 1,
    },
}


class ProductAnalyzer:

    @staticmethod
    async def analyze_product(
        image_url: str,
        selling_points: str = "",
        usage: str = "",
        region: str = "",
        platform: str = "",
        suite_type: str = "premium_aplus",
        count: int = 6,
    ) -> Dict:
        if not region:
            region = "中国"
        if not platform:
            platform = "amazon"

        try:
            user_prompt = ProductAnalyzer._build_prompt(
                selling_points, usage, region, platform, suite_type, count
            )

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
                                {"type": "text", "text": user_prompt},
                            ],
                        }
                    ],
                    "temperature": 0.9,
                },
                timeout=180,
            )

            if resp.status_code != 200:
                print(f"[ANALYZER] 通义千问返回错误: {resp.status_code} {resp.text}")
                return ProductAnalyzer._fallback(platform, suite_type, count, region)

            result_text = resp.json()["choices"][0]["message"]["content"]
            print(f"[ANALYZER] 原始返回: {result_text[:800]}")

            match = re.search(r'\{[\s\S]*\}', result_text)
            if match:
                result = json.loads(match.group(0))
                return result
            else:
                raise Exception("无法解析商品分析结果")

        except Exception as e:
            print(f"[ANALYZER] 分析失败: {e}")
            import traceback
            traceback.print_exc()
            return ProductAnalyzer._fallback(platform, suite_type, count, region)

    @staticmethod
    def _build_prompt(selling_points, usage, region, platform, suite_type, count) -> str:
        spec = SUITE_TYPE_SPECS.get(suite_type, SUITE_TYPE_SPECS["premium_aplus"])

        # ★ 场景图：画布尺寸固定，其他 AI 自由
        if suite_type == "scene":
            layout_instruction = (
                "**布局由你自由决定**：可以全屏图、可以多宫格、可以带文字、可以不带文字。\n"
                "**文案由你自由决定**：可以加标题、可以不加。\n"
                "**场景内容由你自由决定**：环境、构图、角度、人物，全部由你判断。\n"
                "**唯一约束**：画布尺寸必须是 1024x1024，元素不能越界。"
            )
        else:
            layout_instruction = (
                "**每张图的布局要求**：\n"
                "- 元素不重叠（文字不能压图）\n"
                "- 元素不越界\n"
                "- 每张图的布局**不同**（一张中心产品、一张左文右图、一张三宫格、一张上大下二、一张双列……）\n"
                f"- {count} 张图的布局、场景、文案**完全不同**\n"
                f"- 每张图里，AI 图数量在 {spec['min_images_per_canvas']} ~ {spec['max_images_per_canvas']} 之间"
            )

        user_sp = f"\n用户提供的卖点：{selling_points}" if selling_points else ""
        user_usage = f"\n用户提供的用途：{usage}" if usage else ""
        user_region = f"\n销售地区：{region}"
        user_platform = f"\n销售平台：{platform}"
        user_count = f"\n需要生成的图片数量：{count}"

        return f"""你是电商视觉策划专家。分析产品图，输出结构化 JSON。

**语言**：
- 根据 region 决定输出语言（中国→中文，美国→英文，日本→日文，德国→德文，法国→法文，西班牙→西班牙文，韩国→韩文，意大利→意大利文，葡萄牙→葡萄牙文，俄罗斯→俄文，未知→英文）
- 文字字段（product_name、material、category、selling_points、target_audience、main_color、text 元素）用对应语言
- `product_appearance`、`usage_analysis`、`scene_prompt` 必须用**英文**

**套图类型规格（必须严格遵守）**：
- 类型：{spec['name']}（{suite_type}）
- 画布尺寸：{spec['canvas_size']}（所有图的 canvas_size 必须是这个）
- 图片数量：**{count} 张**（images 数组必须有 {count} 个元素）
- 风格：{spec['style']}
- 布局偏好：{spec['layout_preference']}
- 每张图里，AI 图数量：{spec['min_images_per_canvas']} ~ {spec['max_images_per_canvas']} 张

**第一步：分析产品属性**
- `product_name`：商品名
- `material`：材质
- `category`：品类
- `product_appearance`：详细外观描述（英文，200 字以内）
- `usage_analysis`：使用方式（英文，100 字以内）
  - 手持 / 佩戴 / 固定安装 / 放置 / 悬挂？
  - 需要人物参与吗，还是独立存在？
  - 适合什么环境（室内 / 室外 / 厨房 / 车间 / 浴室 / 户外）？
  - 适合什么人群（家庭 / 专业 / 旅行 / 运动）？
  - 核心功能（承重 / 收纳 / 装饰 / 保护 / 计时 / 通讯）？

**第二步：生成 {count} 张图的布局规格**

每张图是一个独立的"画布"，包含若干 `elements`：
- `type: "image"`：AI 生成的图，需要 `scene_prompt`（英文，15-25 词）和 `highlight_feature`（这张图突出的功能卖点）
- `type: "text"`：文案，需要 `text`、`font`、`size`、`color`、`maxLines`

**画布尺寸**：
- 所有图的 `canvas_size` 必须是 {spec['canvas_size']}
- 所有元素的坐标必须在画布范围内（x >= 0, y >= 0, x+w <= 画布宽, y+h <= 画布高）

{layout_instruction}

**功能多样化（必须遵守）**：
- 先提取 6 个 `selling_points`（不同卖点）
- {count} 张图的 `highlight_feature` 必须来自 `selling_points` 里的**不同项**
- **禁止两张图突出同一个卖点**
- `highlight_feature` 必须**具体**，不能是泛泛的词
- 例如：
  - 卖点"50m 防水" → `highlight_feature`: "50m water resistance for swimming"
  - 卖点"EL 背光" → `highlight_feature`: "EL backlight for night visibility"
  - 卖点"双时间" → `highlight_feature`: "dual time zones for travel"
  - 卖点"抗震" → `highlight_feature`: "shock absorption for outdoor use"
  - 卖点"秒表" → `highlight_feature`: "1/100s precision stopwatch"
  - 卖点"长续航" → `highlight_feature`: "long battery life for extended use"

**场景多样化（必须遵守）**：
- {count} 张图的场景必须覆盖以下 **16 种环境类型**，尽可能分散：
  1. 室内家居（客厅、卧室、书房）
  2. 厨房餐厅（厨房、餐厅、咖啡角）
  3. 卫浴空间（浴室、洗手台、淋浴间）
  4. 衣帽间 / 衣柜（衣帽间、衣柜、梳妆台）
  5. 办公场所（办公室、会议室、工位）
  6. 城市环境（街道、地铁、机场、咖啡馆）
  7. 户外自然（森林、山脉、草原、峡谷）
  8. 水边（海滩、湖泊、河流、码头）
  9. 花园 / 庭院（花园、阳台、露台、庭院）
  10. 运动场所（健身房、跑道、球场、泳池）
  11. 交通工具（自行车、汽车、帆船、飞机）
  12. 夜间场景（夜跑、夜街、夜间露营）
  13. 工作场所（车间、工地、实验室、仓库）
  14. 商业空间（商场、超市、店铺、展览馆）
  15. 户外营地（露营地、帐篷、篝火旁）
  16. 特殊场景（沙漠、雪地、温泉、游乐园）
- **禁止 {count} 张图里有超过 2 个是同一环境类型**
- **环境必须匹配产品属性**（手表配户外/运动/办公，不配化妆台；口红配化妆台/派对/商场，不配工地）
- **优先选择"用户日常真实会遇到"的环境**

**每个 scene_prompt 的要求**：
- 15-25 个英文单词，环境为主
- 符合产品使用属性（挂钩是"挂墙上"，不是"戴手腕"）
- 符合产品使用环境
- 可以包含人物，也可以不包含
- {count} 张图的场景**完全不同**（环境、构图、角度、用途都不同）
- 禁止重复
- 环境占画面 70% 以上
- 产品占画面面积不超过 15%
- 如果包含人物，产品和人物错位摆放，产品不能遮挡人物的脸/头/身体

**禁止**：
- 手部特写、产品遮挡人物、产品居中、纯色背景
- 所有场景用同一环境
- 场景和产品不匹配（挂钩配自行车、手表配潜水）
- feature 用泛泛的词（quality / design / value / durability / portability / performance / craftsmanship / practicality）

**用户信息**：{user_sp}{user_usage}{user_region}{user_platform}{user_count}

**输出 JSON（严格格式，无解释）**：

{{
  "product_name": "商品名",
  "material": "材质",
  "category": "品类",
  "target_language": "语言",
  "selling_points": ["卖点1","卖点2","卖点3","卖点4","卖点5","卖点6"],
  "product_appearance": "Detailed English description (max 200 chars)",
  "usage_analysis": "English description of how the product is used (max 100 chars)",
  "platform": "{platform}",
  "region": "{region}",
  "suite_type": "{suite_type}",
  "canvas_size": {spec['canvas_size']},
  "images": [
    {{
      "index": 1,
      "elements": [
        {{"type": "image", "name": "scene_1", "x": 0, "y": 0, "w": 660, "h": 600, "scene_prompt": "English scene 1", "highlight_feature": "卖点1的具体功能"}},
        {{"type": "image", "name": "scene_2", "x": 660, "y": 0, "w": 804, "h": 300, "scene_prompt": "English scene 2", "highlight_feature": "卖点2的具体功能"}},
        {{"type": "image", "name": "scene_3", "x": 660, "y": 300, "w": 804, "h": 300, "scene_prompt": "English scene 3", "highlight_feature": "卖点3的具体功能"}},
        {{"type": "text", "x": 40, "y": 40, "text": "主标题1", "font": "SourceHanSerif-Bold", "size": 48, "color": "#FFFFFF", "maxLines": 2}}
      ]
    }},
    {{
      "index": 2,
      "elements": [
        {{"type": "image", "name": "scene_1", "x": 0, "y": 0, "w": 1464, "h": 600, "scene_prompt": "English scene 1", "highlight_feature": "卖点4的具体功能"}},
        {{"type": "text", "x": 40, "y": 40, "text": "主标题2", "font": "SourceHanSerif-Bold", "size": 56, "color": "#FFFFFF", "maxLines": 2}}
      ]
    }}
    ... 共 {count} 张
  ],
  "target_audience": "目标人群",
  "main_color": "主色调"
}}"""

    @staticmethod
    def _fallback(platform: str, suite_type: str, count: int = 6, region: str = "US") -> Dict:
        """
        AI 失败时返回空结构，触发退款。
        不生成兜底图，避免用户拿到凑数的图。
        """
        print("[ANALYZER] AI 分析失败，返回空结构（将触发退款）")
        spec = SUITE_TYPE_SPECS.get(suite_type, SUITE_TYPE_SPECS["premium_aplus"])
        return {
            "product_name": "",
            "material": "",
            "category": "",
            "target_language": "英语",
            "selling_points": [],
            "product_appearance": "",
            "usage_analysis": "",
            "platform": platform,
            "region": region,
            "suite_type": suite_type,
            "canvas_size": spec["canvas_size"],
            "images": [],
            "target_audience": "",
            "main_color": "",
            "_fallback": True,
        }


product_analyzer = ProductAnalyzer()