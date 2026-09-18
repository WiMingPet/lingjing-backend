"""
商品分析服务 - 使用 qwen-vl-plus 分析商品图
"""
import base64
import requests
import json
import re
from app.config import settings


class ProductAnalyzer:
    """商品分析器"""
    
    # 语言映射
    LANGUAGE_MAP = {
        "中国大陆": "中文", "中国": "中文",
        "美国": "英语", "英国": "英语",
        "日本": "日语", "德国": "德语",
        "法国": "法语", "西班牙": "西班牙语",
        "意大利": "意大利语", "巴西": "葡萄牙语",
        "俄罗斯": "俄语", "韩国": "韩语",
    }
    
    @staticmethod
    async def analyze_product(
        image_url: str,
        selling_points: str = "",
        usage: str = "",
        region: str = "",
        platform: str = "",
    ) -> dict:
        """分析商品图，提取结构化信息"""
        # 下载图片
        resp = requests.get(image_url, timeout=30)
        img_base64 = base64.b64encode(resp.content).decode('utf-8')
        
        # 确定目标语言
        target_language = ProductAnalyzer.LANGUAGE_MAP.get(region, "英语")
        
        # 用户补充信息
        user_info = ""
        if selling_points:
            user_info += f"\n- 卖点：{selling_points}"
        if usage:
            user_info += f"\n- 使用方式：{usage}"
        if region:
            user_info += f"\n- 销售地区：{region}"
        if platform:
            user_info += f"\n- 发布平台：{platform}"
        
        prompt = f"""你是电商场景图策划专家。请分析这张商品图，提取以下信息：

1. 商品名称（具体到款式、类型）
2. 商品材质
3. 商品品类
4. 核心卖点（**必须生成 6-8 条**，每条不超过 15 字，用{target_language}输出）
5. 产品外观描述（用英文，极其详细）：
   - 主色调、次要颜色
   - 形状、轮廓
   - 材质和表面质感
   - 所有可辨识的文字、数字、图标、刻度、图案
   - 特殊细节（螺丝、按钮、链条、logo、纹理等）
6. 场景描述（**必须生成至少 12 个不同的场景**，用英文）：
   - 每个场景必须对应一个卖点
   - 场景描述里绝对不能出现产品名称或产品词
   - 只描述环境、光线、氛围、空间、人物动作

**卖点数量要求**：
- selling_points 必须生成 6-8 个不同卖点（不是 3-5 个）
- scene_prompts 必须生成 12 个以上
- 每个卖点至少配 2 个场景

**互动方式多样化**：
- 根据产品品类推断可能的互动方式（佩戴/手持/静置/使用中/收纳/展示）
- 互动方式必须符合产品品类的物理逻辑
- 每个场景标明 interaction

**场景环境多样化（最重要）**：
- 同一互动方式下，环境必须不同（例如"戴在手腕上"可以出现在：篝火露营、攀岩中途、会议室、山顶日出、雨中跑步、咖啡厅）
- 场景必须覆盖 sport/life/work/outdoor/leisure 中的至少 3 类
- 每个场景标明 scene_type

**关于用户卖点**：
- 用户提供了卖点就优先用
- 用户卖点只决定"突出什么功能"，不决定"用什么场景"
- 一个卖点必须配 2 种以上完全不同类型的场景

用户补充信息（如有）：{user_info}

要求：
- 输出严格 JSON 格式，不要其他内容
- product_appearance 用英文
- 卖点和场景描述用{target_language}输出
- scene_prompts 必须至少 12 个
- 每个 scene_prompt 必须包含 interaction 和 scene_type

输出格式：
{{
    "product_name": "商品名称",
    "material": "材质",
    "category": "品类",
    "selling_points": ["卖点1", "卖点2", "卖点3", "卖点4", "卖点5", "卖点6"],
    "product_appearance": "Detailed English description",
    "scene_prompts": [
        {{"selling_point": "卖点1", "scene": "English scene 1", "interaction": "worn on body", "scene_type": "outdoor"}},
        {{"selling_point": "卖点1", "scene": "English scene 2", "interaction": "worn on body", "scene_type": "sport"}},
        {{"selling_point": "卖点2", "scene": "English scene 3", "interaction": "held in hand", "scene_type": "work"}},
        {{"selling_point": "卖点2", "scene": "English scene 4", "interaction": "held in hand", "scene_type": "life"}},
        {{"selling_point": "卖点3", "scene": "English scene 5", "interaction": "placed on surface", "scene_type": "leisure"}},
        {{"selling_point": "卖点3", "scene": "English scene 6", "interaction": "placed on surface", "scene_type": "work"}},
        {{"selling_point": "卖点4", "scene": "English scene 7", "interaction": "in use", "scene_type": "sport"}},
        {{"selling_point": "卖点4", "scene": "English scene 8", "interaction": "in use", "scene_type": "outdoor"}},
        {{"selling_point": "卖点5", "scene": "English scene 9", "interaction": "worn on body", "scene_type": "life"}},
        {{"selling_point": "卖点5", "scene": "English scene 10", "interaction": "stored in bag", "scene_type": "leisure"}},
        {{"selling_point": "卖点6", "scene": "English scene 11", "interaction": "displayed on stand", "scene_type": "work"}},
        {{"selling_point": "卖点6", "scene": "English scene 12", "interaction": "held in hand", "scene_type": "outdoor"}}
    ],
    "target_audience": "目标人群",
    "main_color": "主色调"
}}"""
        
        try:
            response = requests.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "qwen-vl-plus",
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
                        ]
                    }],
                    "max_tokens": 2000,
                    "temperature": 0.5
                },
                timeout=60
            )
            
            content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"[ANALYZER] 原始返回: {content[:300]}")
            
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                result = json.loads(match.group(0))
                result["target_language"] = target_language
                result["region"] = region
                result["platform"] = platform
                return result
            else:
                raise Exception("无法解析商品分析结果")
        
        except Exception as e:
            print(f"[ANALYZER] 分析失败: {e}")
            return {
                "product_name": "商品",
                "material": "未知",
                "category": "通用",
                "selling_points": ["High Quality", "Great Value", "Best Choice"],
                "product_appearance": "A product with distinct colors, materials, and details as shown in the reference image",
                "scene_prompts": [
                    {"selling_point": "High Quality", "scene": "A person holding the product while running on a mountain trail, natural sunlight, dynamic motion"},
                    {"selling_point": "High Quality", "scene": "The product placed on a wooden desk in a bright modern office, soft window light"},
                    {"selling_point": "High Quality", "scene": "The product on a marble kitchen counter, morning light, minimal styling"},
                    {"selling_point": "Great Value", "scene": "A person using the product in a sunny outdoor park, green trees, natural light"},
                    {"selling_point": "Great Value", "scene": "A person using the product during light rain on a city street, wet pavement reflections"},
                    {"selling_point": "Great Value", "scene": "The product on a sandy beach at golden hour, ocean waves in background"},
                    {"selling_point": "Best Choice", "scene": "A person holding the product in a modern gym, blurred workout equipment, dramatic lighting"},
                    {"selling_point": "Best Choice", "scene": "The product on a café table with a coffee cup, warm ambient light"},
                    {"selling_point": "Best Choice", "scene": "A person using the product in a forest hiking trail, dappled sunlight through trees"},
                    {"selling_point": "High Quality", "scene": "The product on a clean studio surface with soft gradient background, product close-up"},
                ],
                "target_audience": "大众",
                "main_color": "白色",
                "target_language": target_language,
                "region": region,
                "platform": platform,
            }


product_analyzer = ProductAnalyzer()