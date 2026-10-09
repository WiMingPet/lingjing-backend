"""
剧本生成服务：通义千问根据"提示词 + 参考图"生成剧本
"""
import json
import re
import requests
import asyncio
from typing import Dict
from app.config import settings


class ScriptGenerator:

    @staticmethod
    async def generate_script(theme: str, duration: int, style: str = "",
                            reference_count: int = 0, reference_info: list = None,
                            language: str = "zh", mode: str = "real") -> Dict:
        """生成剧本"""
        if duration == 1:
            scene_count = 6       # 1 分钟 = 6 个 10 秒
        elif duration == 3:
            scene_count = 18      # 3 分钟 = 18 个 10 秒
        else:
            scene_count = 30      # 5 分钟 = 30 个 10 秒

        # ★ 动漫短剧：AI 自动匹配国产 3D 动画风（真人短剧不加，prompt 不变）
        # ========== 画风映射 ==========
        if mode == "real":
            mode_hint = ""   # 真人，不加画风提示
        elif mode == "anime_cn":
            mode_hint = """
**画风要求（重要）**：这是**国产 3D 动画短剧**，所有角色和场景必须是**国产 3D 动画风格**（类似哪吒之魔童降世、姜子牙、白蛇缘起）。
- 角色 appearance 必须包含：Chinese 3D animation, donghua 3D, CGI character
- scene_prompt 必须包含：Chinese 3D animation, donghua 3D, CGI scene
- 不要出现 2D、anime style、cel shading、photorealistic 等词
- 角色要立体、有质感、有细节，场景要空间感强、光影丰富
- 剧情可以偏热血、奇幻、夸张，符合 3D 动画叙事
"""
        elif mode == "anime_jp":
            mode_hint = """
**画风要求（重要）**：这是**日漫 2D 动画短剧**，所有角色和场景必须是**日系 2D 动画风格**（类似火影忍者、鬼灭之刃、你的名字）。
- 角色 appearance 必须包含：Japanese anime style, 2D illustration, cel shading, clean line art
- scene_prompt 必须包含：Japanese anime style, 2D illustration, cel shading
- 不要出现 3D、realistic、photorealistic 等词
- 角色要有大眼睛、简化五官、清晰描边，场景要日系动画质感
- 剧情可以偏热血、日常、奇幻，符合日漫叙事
"""
        elif mode == "anime_pixar":
            mode_hint = """
**画风要求（重要）**：这是**皮克斯/迪士尼 3D 动画短剧**，所有角色和场景必须是**皮克斯/迪士尼 3D 动画风格**（类似玩具总动员、寻梦环游记、冰雪奇缘）。
- 角色 appearance 必须包含：Pixar style, Disney 3D animation, CGI character, cute and stylized
- scene_prompt 必须包含：Pixar style, Disney 3D animation, CGI scene
- 不要出现 2D、anime、cel shading、photorealistic 等词
- 角色要立体、可爱、有质感，场景要温暖、治愈
- 剧情可以偏温暖、治愈、适合全家
"""
        elif mode == "anime_us":
            mode_hint = """
**画风要求（重要）**：这是**美漫 2D 动画短剧**，所有角色和场景必须是**美式漫画 2D 动画风格**（类似蜘蛛侠：平行宇宙、漫威动画）。
- 角色 appearance 必须包含：American comic style, 2D animation, bold outlines, vibrant colors
- scene_prompt 必须包含：American comic style, 2D animation, bold outlines
- 不要出现 3D、anime、cel shading、photorealistic 等词
- 角色要硬朗、有力量感、色彩饱和，场景要有美漫质感
- 剧情可以偏英雄、冒险、科幻，符合美漫叙事
"""
        else:
            mode_hint = ""

        # ★ 语言映射
        lang_map = {
            "zh": "中文（普通话）",
            "ja": "日本語",
            "en": "English",
            "fr": "Français",
            "ko": "한국어",
            "dongbei": "东北话",
            "sichuan": "四川话",
            "chongqing": "重庆话",
            "yue": "粤语（Cantonese）",
            "nan": "闽南语（Hokkien）",
        }
        lang_name = lang_map.get(language, "中文（普通话）")

        # ★ 方言提示
        if language in ("dongbei", "sichuan", "chongqing", "yue", "nan"):
            lang_hint = f"""
**输出语言**：{lang_name}（方言）

**注意**：
- **所有"对话"（dialogue.text）必须用"{lang_name}"的"方言表达"**，不要用"普通话"。
- **其他字段（title、summary、name）可以用"普通话"**，方便"阅读"。
- **appearance 和 scene_prompt 用英文**（因为要传给 AI 生图模型）。
"""
        else:
            lang_hint = f"""
**输出语言**：{lang_name}

**所有"文字字段"必须用 {lang_name} 输出**：
- title、summary、name、dialogue.text

**appearance 和 scene_prompt 用英文**（因为要传给 AI 生图模型）。
"""

        # 根据"是否有参考图"，生成不同的提示
        if reference_count > 0 and reference_info:
            # ★ 有分析结果：用视觉模型分析出的性别/年龄/外貌匹配
            ref_desc = "\n".join([
                f"- 图 {info['reference_index']}: 性别={info.get('gender', 'unknown')}, "
                f"年龄={info.get('age_range', 'unknown')}, "
                f"外貌={info.get('appearance', '')}"
                for info in reference_info
            ])
            ref_rule = f"""
**用户上传了 {reference_count} 张参考图，已通过视觉模型分析如下**：

{ref_desc}

**角色分配规则**：
- 根据每张参考图的**性别、年龄、外貌**，自动匹配最合适的角色
- 为匹配的角色添加 `reference_index` 字段（对应图号 1~N）
- 其他角色 `reference_index` 为 0
- **匹配依据**：
  - 性别必须一致（male 配 male，female 配 female）
  - 年龄尽量接近（如 mid 20s 配 young adult）
  - 外貌特征相符（发型、气质）
- **如果用户提示词里明确说了"图 X 是 XXX"，以用户说的为准**
- **如果有多张参考图，按用户说明或 AI 自动匹配**

**示例**：
- 图 1 是 female, mid 20s → 匹配到女性主角
- 图 2 是 male, early 30s → 匹配到男性主角

**输出示例**：
{{
  "characters": [
    {{"name": "王丽", "role": "main", "reference_index": 1, "appearance": "Chinese female..."}},
    {{"name": "李明", "role": "main", "reference_index": 2, "appearance": "Chinese male..."}},
    {{"name": "张华", "role": "supporting", "reference_index": 0, "appearance": "..."}}
  ]
}}
"""
        elif reference_count > 0:
            # 兜底：没分析结果时，沿用旧的 ref_rule
            ref_rule = f"""
**用户上传了 {reference_count} 张参考图**。

**角色来源规则**：
- 用户会在"主题/提示词"里说明每张参考图的角色，例如"图 1 是唐僧，图 2 是孙悟空"
- **你必须仔细阅读用户的提示词，识别出"哪张图对应哪个角色"**
- 为每个角色添加 `reference_index` 字段：
  - `reference_index`: 1~N（对应第 N 张参考图）
  - `reference_index`: 0（没有参考图，AI 生成）
- **如果用户"没说清楚"，你根据"主题"自行推断**

**示例**：
用户输入："图 1 是唐僧，图 2 是孙悟空，图 3 是猪八戒。主题：三打白骨精。"
输出：
{{
  "characters": [
    {{"name": "唐僧", "role": "main", "reference_index": 1, "appearance": "..."}},
    {{"name": "孙悟空", "role": "main", "reference_index": 2, "appearance": "..."}},
    {{"name": "猪八戒", "role": "main", "reference_index": 3, "appearance": "..."}},
    {{"name": "白骨精", "role": "supporting", "reference_index": 0, "appearance": "..."}}
  ]
}}
"""
        else:
            ref_rule = """
**用户没有上传参考图**。
所有角色由 AI 生成，`reference_index` 全部为 0。
"""

        prompt = f"""你是一个专业的短剧编剧。根据用户输入，生成一个完整的短剧剧本。

**用户输入的主题/提示词**：
{theme}

**总时长**：{duration} 分钟
**分镜数**：{scene_count} 个（每个 10 秒）

{mode_hint}

{lang_hint}

{ref_rule}

**核心规则**：

**1. 角色分类**：
- "main"（主角）：2~3 个，必须有定妆照
- "supporting"（配角）：2~5 个
- "extra"（群众演员）：N 个，不生成定妆照

**2. 角色外观（appearance）**：
- **英文**，20-40 词
- 必须包含"人种/国籍"，根据主题推断：
  - 古装/中国主题 → Chinese, Asian
  - 日式主题 → Japanese
  - 欧美主题 → American / European
  - 其他 → 根据主题判断
- 必须包含：年龄 + 性别 + 发型 + 服装 + 特征

**3. 分镜设计**：
- 每个分镜 = 一个场景 + 多个角色 + **明确动作过程**
- scene_prompt 英文，20-40 词
- characters_in_scene 包含所有出场角色
- 场景必须多样化
- 剧情要有"起承转合"

**3.1 动作连贯性（重要，通用要求）**：
- 每个分镜的 `scene_prompt` 必须包含**明确动作**，不是静态场景
- 格式建议：`[角色] is [doing action], [角色] [does another action], ...`
- ✅ 好例子（通用，不限剧情）：
  - "A man walks into the room, looks around, then sits on the chair"
  - "A woman picks up a cup, drinks, then puts it down"
- ❌ 差例子：
  - "A man in the room"（没动作）
  - "A busy street scene"（没动作）
- **每个分镜的"结尾动作"，要能衔接下一个分镜的"开头动作"**
- 每个分镜额外输出 `end_action` 字段（英文，10-20 词），描述"这个分镜的结尾动作"

**3.2 剧情连贯性（重要，通用要求）**：
- {scene_count} 个分镜是一条**完整时间线**，前后逻辑连贯
- 每个分镜的开头必须承接上一个分镜的结尾
- 不允许场景、人物、情绪突变
- 剧情结构：
  - 第 1 个分镜：建立冲突/悬念
  - 中间分镜：升级/铺垫
  - 倒数第 2 个：反转/高潮
  - 最后 1 个：结局

**4. 对话（类型自适应）**：

**4.0 类型判断（重要）**：
- 根据用户输入的"主题/提示词"自动判断短剧类型
- 不同类型用不同结构、不同台词风格
- **不要所有类型都用"逆袭打脸"套路**

**4.1 对话基本要求**：
- 每个分镜 **4~8 句**
- 对话 **20~50 字**（**用 {lang_name}**）
- 对话要紧凑、有冲突、有情绪
- 每句对白都要推动剧情
- 禁止无意义的寒暄

**4.2 剧情结构（根据类型自适应）**：
- 逆袭/复仇 → 冲突 → 隐忍 → 反转 → 打脸
- 甜宠/爱情 → 相遇 → 心动 → 误会 → 和好
- 悬疑/推理 → 案件 → 线索 → 反转 → 真相
- 家庭/伦理 → 矛盾 → 冲突 → 理解 → 和解
- 古装/宫斗 → 争斗 → 结盟 → 背叛 → 胜利
- 搞笑/日常 → 冲突 → 升级 → 反转 → 笑点
- 根据主题选择最适合的结构
- 每个分镜必须有"钩子"：让观众想看下一段

**4.3 台词风格（根据类型自适应）**：
- 逆袭/复仇 → 短、有力、打脸
- 甜宠/爱情 → 温柔、暧昧、甜
- 悬疑/推理 → 冷峻、暗示、伏笔
- 家庭/伦理 → 真实、扎心、温情
- 不要所有类型都用"打脸"风格

**4.4 情绪与动作**：
- 对话要带"情绪"
- 可以用"动作"辅助情绪：甩手、冷笑、转身、跪下

**5. 输出格式**：

{{
  "title": "短剧标题",
  "summary": "一句话简介",
  "characters": [
    {{"name": "角色名", "role": "main", "reference_index": 0, "appearance": "English, 20-40 words"}}
  ],
  "scenes": [
    {{
      "index": 1,
      "scene_prompt": "English scene with clear actions, 20-40 words",
      "end_action": "English, the ending action of this scene, 10-20 words",
      "characters_in_scene": ["角色名1", "角色名2"],
      "dialogue": [
        {{"character": "角色名", "text": "对话（用 {lang_name}）"}}
      ]
    }}
  ]
}}

**注意**：
- characters 数组必须有"所有角色"
- scenes 数组必须有 {scene_count} 个元素
- scenes 数组每个元素必须有 `end_action` 字段（这个分镜的结尾动作）
- **所有剧情由你根据用户输入"自由生成"，不要套用任何"固定剧情"**
"""

        def _sync():
            resp = requests.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "qwen-max",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.9,
                },
                timeout=300,
            )
            if resp.status_code != 200:
                raise Exception(f"通义千问错误: {resp.status_code} {resp.text[:200]}")
            text = resp.json()["choices"][0]["message"]["content"]
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                return json.loads(match.group(0))
            raise Exception("无法解析剧本")

        return await asyncio.to_thread(_sync)


script_generator = ScriptGenerator()