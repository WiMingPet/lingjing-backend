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
    async def _expand_to_outline(theme: str, duration: int, language: str, mode: str) -> str:
        """把一句话主题，展开成几百字大纲"""
        
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
        
        # 根据时长决定场景数
        if duration == 1:
            scene_hint = "1 个场景"
        elif duration <= 3:
            scene_hint = "1~2 个场景"
        elif duration <= 6:
            scene_hint = "2~3 个场景"
        else:
            scene_hint = "3~5 个场景"
        
        prompt = f"""你是一个专业的短剧编剧。用户给了一句话：
"{theme}"

**你的任务**：把这句话展开成一个"几百字的短剧大纲"。

**大纲必须包含**：

1. **场景**：{scene_hint}
2. **人物**：3~5 个，每个有名字、年龄、身份、性格
3. **三幕结构**：
   - 第 1 幕：**羞辱/危机**（谁羞辱谁，为什么，情绪最低点）
   - 第 2 幕：**反转**（主角怎么反击，亮出什么底牌，全场震惊）
   - 第 3 幕：**打脸/高潮**（主角怎么碾压反派，反派什么反应，主角潇洒离场）
4. **情绪弧线**：从低到高

**要求**：
- 具体、有冲突、有爆点
- 根据主题判断类型（逆袭/甜宠/悬疑/家庭/古装/搞笑/科幻/恐怖/文艺/儿童）
- 按对应类型写三幕
- 用 {lang_name} 输出
- 200~500 字

**输出格式**（纯文本，不要 JSON，不要 markdown）：

场景：xxx

人物：
- 角色1：年龄、身份、性格
- 角色2：...

情节：
第 1 幕（羞辱）：...
第 2 幕（反转）：...
第 3 幕（打脸）：...
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
            return resp.json()["choices"][0]["message"]["content"].strip()
        
        return await asyncio.to_thread(_sync)

    @staticmethod
    async def generate_script(theme: str, duration: int, style: str = "",
                            reference_count: int = 0, reference_info: list = None,
                            language: str = "zh", mode: str = "real") -> Dict:
        """生成剧本"""
        
        # ★ 如果用户输入很短（< 50 字），先让 AI 展开成"几百字大纲"
        if len(theme.strip()) < 50:
            print(f"[SCRIPT] 用户输入很短（{len(theme)} 字），先展开成大纲...")
            theme = await ScriptGenerator._expand_to_outline(theme, duration, language, mode)
            print(f"[SCRIPT] 展开后大纲（{len(theme)} 字）")
        
        # ========== 下面保持原逻辑 ==========
        
        if duration == 1:
            scene_count = 6
        elif duration == 3:
            scene_count = 18
        elif duration == 5:
            scene_count = 30
        elif duration == 6:
            scene_count = 36
        elif duration == 10:
            scene_count = 60
        else:
            scene_count = 30

        # ★ 画风映射
        if mode == "real":
            mode_hint = ""
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

        if language in ("dongbei", "sichuan", "chongqing", "yue", "nan"):
            lang_hint = f"""
**输出语言**：{lang_name}（方言）

**注意**：
- **所有"对话"（dialogue.text）必须用"{lang_name}"的"方言表达"**。
- **其他字段（title、summary、name）可以用"普通话"**。
- **appearance 和 scene_prompt 用英文**。
"""
        else:
            lang_hint = f"""
**输出语言**：{lang_name}

**所有"文字字段"必须用 {lang_name} 输出**：
- title、summary、name、dialogue.text

**appearance 和 scene_prompt 用英文**。
"""

        # ★ 参考图规则
        if reference_count > 0 and reference_info:
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
- **如果用户提示词里明确说了"图 X 是 XXX"，以用户说的为准**
"""
        elif reference_count > 0:
            ref_rule = f"""
**用户上传了 {reference_count} 张参考图**。

**角色来源规则**：
- 用户会在"主题/提示词"里说明每张参考图的角色
- 为每个角色添加 `reference_index` 字段：1~N 或 0
- **如果用户"没说清楚"，你根据"主题"自行推断**
"""
        else:
            ref_rule = """
**用户没有上传参考图**。
所有角色由 AI 生成，`reference_index` 全部为 0。
"""

        prompt = f"""你是一个专业的短剧编剧。用户会给你**一段剧情**（可能是主题，也可能是大纲），你只需要讲**这段剧情的前 {duration} 分钟**。

**核心原则（重要）**：
- 用户输入的可能是"一句话主题"或"几百字大纲"
- 如果是**一句话主题**：你自由发挥
- 如果是**几百字大纲**：你**严格按大纲执行**
  - 用户写的**角色**，必须全部用（不改名、不改设定）
  - 用户写的**场景**，必须出现
  - 用户写的**情节**，必须保留（顺序不打乱）
  - 用户写的**对白**（如果有），优先用
- 你只需要讲**这段剧情的前 {duration} 分钟**
- **不要求讲完整个故事**
- 用户会自己拼接多段素材
- **每一段必须是连续的，不跳跃**

**用户输入**：
{theme}

**总时长**：{duration} 分钟
**分镜数**：{scene_count} 个（每个 10 秒）

{mode_hint}

{lang_hint}

{ref_rule}

**核心规则**：

**1. 角色分类**：
- "main"（主角）：2~3 个
- "supporting"（配角）：2~5 个
- "extra"（群众演员）：N 个

**2. 角色外观（appearance）**：
- **英文**，20-40 词
- 包含：人种 + 年龄 + 性别 + 发型 + 服装 + 特征

**3. 分镜设计**：
- 每个分镜 = 一个场景 + 多个角色 + **明确动作**
- scene_prompt 英文，20-40 词
- characters_in_scene 包含所有出场角色

**3.1 动作连贯性（重要）**：
- 每个分镜的 `scene_prompt` 必须包含**明确动作**
- **每个分镜的"结尾动作"，要能衔接下一个分镜的"开头动作"**
- 每个分镜额外输出 `end_action` 字段

**3.2 剧情连贯性（重要）**：
- {scene_count} 个分镜是一条**完整时间线**
- 每个分镜的开头必须承接上一个分镜的结尾

**3.3 三幕结构（重要，核心规则）**：

**1 分钟短剧必须有"三幕"**：
- **第 1 幕（前 1/3）**：羞辱/危机（情绪最低点）
- **第 2 幕（中 1/3）**：反转（主角反击，全场震惊）
- **第 3 幕（后 1/3）**：打脸/高潮（主角碾压，反派崩溃）

**每一幕拆成 2~3 个分镜**：
- 分镜 1：动作起点
- 分镜 2：动作过程
- 分镜 3：反应

**禁止**：
- 一个分镜跳过整个"幕"
- 只给"结果"不给"过程"

**3.4 场景统一性（重要，核心规则）**：

- **1 分钟（6 分镜）**：**只允许 1 个场景**
- **3 分钟（18 分镜）**：允许 1~2 个场景
- **5/6 分钟（30/36 分镜）**：允许 2~3 个场景
- **10 分钟（60 分镜）**：允许 3~5 个场景

**换场景必须有过渡**：
- 动作过渡（角色走出一个场景）
- 时间过渡（字幕"第二天"）
- 因果过渡（上一个场景导致下一个）

**每个场景内部不换地点、不换时间。**

**3.5 戏剧弧线（重要）**：
- 情绪由低到高
- 第 1 幕：情绪最低
- 第 2 幕：情绪逆转
- 第 3 幕：情绪最高
- 每个分镜必须有"钩子"

**4. 对话（类型自适应）**：

**4.1 对话基本要求**：
- 每个分镜 **4~8 句**
- 对话 **20~50 字**（**用 {lang_name}**）
- 对话要紧凑、有冲突、有情绪
- 每句对白都要推动剧情
- 禁止无意义的寒暄

**4.2 剧情结构（根据类型自适应，覆盖 10 大类）**：
- 逆袭/复仇 → 冲突 → 隐忍 → 反转 → 打脸
- 甜宠/爱情 → 相遇 → 心动 → 误会 → 和好
- 悬疑/推理 → 案件 → 线索 → 反转 → 真相
- 家庭/伦理 → 矛盾 → 冲突 → 理解 → 和解
- 古装/宫斗 → 争斗 → 结盟 → 背叛 → 胜利
- 搞笑/日常 → 冲突 → 升级 → 反转 → 笑点
- 科幻/未来 → 危机 → 探索 → 反转 → 拯救
- 恐怖/惊悚 → 平静 → 异样 → 惊吓 → 逃脱
- 文艺/情感 → 情绪 → 回忆 → 领悟 → 释怀
- 儿童/成长 → 问题 → 尝试 → 帮助 → 成功
- 根据主题自动判断类型，选择最适合的结构

**4.3 台词风格（根据类型自适应）**：
- 逆袭/复仇 → 短、有力、打脸
- 甜宠/爱情 → 温柔、暧昧、甜
- 悬疑/推理 → 冷峻、暗示、伏笔
- 家庭/伦理 → 真实、扎心、温情
- 古装/宫斗 → 古风、含蓄、机锋
- 搞笑/日常 → 轻松、吐槽、反转
- 科幻/未来 → 理性、专业、警示
- 恐怖/惊悚 → 压抑、断续、暗示
- 文艺/情感 → 诗意、克制、留白
- 儿童/成长 → 简单、直白、温暖
- 不要所有类型都用"打脸"风格

**5. 输出格式**：

{{
  "title": "标题",
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
- scenes 数组每个元素必须有 `end_action` 字段
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