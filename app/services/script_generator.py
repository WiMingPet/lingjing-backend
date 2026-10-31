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
        
        prompt = f"""你是一个专业的短剧编剧。用户给了一句话：
"{theme}"

**你的任务**：从这句话里，**只提取“一个场景”**，展开成一个"几百字的大纲"。

**场景的定义（重要，通用，不限于任何题材）**：
- **一个地点**：具体的空间
- **一段时间**：30 秒到 1 分钟（短剧节奏，紧凑）
- **多个角色**：2~10 个角色在场（两人对话 2 个，群戏 6~10 个，由题材决定）
- **有冲突**：角色之间有矛盾、有张力
- **有起承转合**：建立 → 冲突 → 升级 → 反转/钩子

**核心原则**：
- 用户这句话，可能包含"多个场景"（如 A → B → C）
- **你只提取"第一个场景"**
- **不要推进到下一个场景**
- 但**这个场景内部要有起承转合**
- 用户会自己拼接多个场景

**判断方法**：
- 用户输入通常包含"多个场景"（如 A → B → C）
- 你**只提取"第一个场景"**
- 把这个场景**内部的细节**讲细
- **不要**讲"第二、第三个场景"

**场景的粒度**：
- ❌ 太小："[角色A]站在门口"（没有冲突、没有变化）
- ✅ 适中："饭桌上，富豪被当众嘲讽，他不动声色，结尾露出名表"（有冲突、有反转）
- ❌ 太大："整个同学聚会"（包含多个场景，30 秒讲不完）

**大纲必须包含**：

1. **人物**：数量由场景类型决定（两人场景 2~3 个，群戏 6~10 个），每个有名字、年龄、身份、性格
2. **场景**：地点、时间、氛围
3. **这个场景的起承转合**：
   - 建立：谁在场、什么氛围
   - 冲突：谁和谁有矛盾
   - 升级：矛盾怎么激化
   - 反转/钩子：结尾留什么悬念
4. **情绪弧线**：从低到高（在这个场景内）

**要求**：
- **只讲"一个场景"**，不推进到下一个场景
- 把这个场景的起承转合写细
- 用 {lang_name} 输出
- 200~500 字

**输出格式**（纯文本，不要 JSON，不要 markdown）：

场景：xxx

人物：
- 角色1：年龄、身份、性格
- 角色2：...

起承转合：
- 建立：...
- 冲突：...
- 升级：...
- 反转/钩子：...
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
        
        # ★ 单段 30 秒（4.0 智能分镜，分秒脚本）
        scene_count = 1

        # ★ 画风映射（不变）
        if mode == "real":
            mode_hint = ""
        elif mode == "anime_cn":
            mode_hint = """
**画风要求（重要）**：这是**国产 3D 动画短剧**，所有角色和场景必须是**国产 3D 动画风格**（类似哪吒之魔童降世、姜子牙、白蛇缘起）。
- 角色 appearance 必须包含：Chinese 3D animation, donghua 3D, CGI character
- shot_prompt 必须包含：Chinese 3D animation, donghua 3D, CGI scene
- 不要出现 2D、anime style、cel shading、photorealistic 等词
- 角色要立体、有质感、有细节，场景要空间感强、光影丰富
- 剧情可以偏热血、奇幻、夸张，符合 3D 动画叙事
"""
        elif mode == "anime_jp":
            mode_hint = """
**画风要求（重要）**：这是**日漫 2D 动画短剧**，所有角色和场景必须是**日系 2D 动画风格**（类似火影忍者、鬼灭之刃、你的名字）。
- 角色 appearance 必须包含：Japanese anime style, 2D illustration, cel shading, clean line art
- shot_prompt 必须包含：Japanese anime style, 2D illustration, cel shading
- 不要出现 3D、realistic、photorealistic 等词
- 角色要有大眼睛、简化五官、清晰描边，场景要日系动画质感
- 剧情可以偏热血、日常、奇幻，符合日漫叙事
"""
        elif mode == "anime_pixar":
            mode_hint = """
**画风要求（重要）**：这是**皮克斯/迪士尼 3D 动画短剧**，所有角色和场景必须是**皮克斯/迪士尼 3D 动画风格**（类似玩具总动员、寻梦环游记、冰雪奇缘）。
- 角色 appearance 必须包含：Pixar style, Disney 3D animation, CGI character, cute and stylized
- shot_prompt 必须包含：Pixar style, Disney 3D animation, CGI scene
- 不要出现 2D、anime、cel shading、photorealistic 等词
- 角色要立体、可爱、有质感，场景要温暖、治愈
- 剧情可以偏温暖、治愈、适合全家
"""
        elif mode == "anime_us":
            mode_hint = """
**画风要求（重要）**：这是**美漫 2D 动画短剧**，所有角色和场景必须是**美式漫画 2D 动画风格**（类似蜘蛛侠：平行宇宙、漫威动画）。
- 角色 appearance 必须包含：American comic style, 2D animation, bold outlines, vibrant colors
- shot_prompt 必须包含：American comic style, 2D animation, bold outlines
- 不要出现 3D、anime、cel shading、photorealistic 等词
- 角色要硬朗、有力量感、色彩饱和，场景要有美漫质感
- 剧情可以偏英雄、冒险、科幻，符合美漫叙事
"""
        else:
            mode_hint = ""

        # ★ 语言映射（不变）
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
- **appearance 和 shot_prompt 用英文**。
"""
        else:
            lang_hint = f"""
**输出语言**：{lang_name}

**所有"文字字段"必须用 {lang_name} 输出**：
- title、summary、name、dialogue.text

**appearance 和 shot_prompt 用英文**。
"""

        # ★ 参考图规则（不变）
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

        # ★ JSON 示例（关键改动：vibe/outfit + 分秒脚本）
        json_example = f'''{{
  "title": "标题",
  "summary": "一句话简介",
  "characters": [
    {{
      "name": "角色名",
      "role": "main",
      "reference_index": 0,
      "appearance": "English, 20-40 words, 人种/年龄/性别/发型/五官/体型/服装",
      "vibe": "English, 3-6 words, 如 wealthy high-status confident",
      "outfit": "English, 5-12 words, 如 bespoke tailored suit premium fabric"
    }}
  ],
  "scenes": [
    {{
      "index": 1,
      "shot_prompt": "30秒分秒脚本，严格按时间点切镜头：\\n0~3秒：特写，[具体画面]\\n3~6秒：中景，[具体画面]\\n6~9秒：[角色名]（[语气]）：\\"[台词]\\"\\n...（每 2~4 秒一个镜头，共 8~12 个镜头）\\n28~30秒：[结尾画面]\\n无字幕。",
      "end_action": "这一段的结尾动作，10-20字",
      "characters_in_scene": ["角色名1", "角色名2"],
      "dialogue": [
        {{"character": "角色名", "tone": "语气", "text": "台词（用 {lang_name}）"}}
      ]
    }}
  ]
}}'''

        prompt = f"""你是一个专业的短剧编剧。用户会给你**一段剧情**（可能是主题，也可能是大纲），你只需要讲**这段剧情的一个 30 秒精彩片段**。

**核心原则（重要）**：
- 用户输入的可能是"一句话主题"或"几百字大纲"
- **根据输入类型，采取不同策略**：
  - **一句话主题** → 你提取"一个场景的一个冲突点"，展开讲细
  - **几百字大纲** → 你**严格按大纲执行**，不提取、不删减
- **只生成 1 段 30 秒**，不讲完整故事，只讲一个"精彩片段"

**题材自适应（重要）**：
- 根据用户输入的主题，判断题材（现代都市、古装、科幻、恐怖、甜宠等）
- 场景、服装、道具、语言风格，必须符合题材
- 不要所有题材都用"现代都市"风格
- 例：
  - 古装宫斗 → 宫殿、华服、古风对白
  - 科幻未来 → 飞船、霓虹、科技感
  - 恐怖悬疑 → 阴暗、潮湿、压抑
  - 甜宠爱情 → 明亮、温暖、浪漫

**用户输入**：
{theme}

**总时长**：30 秒（单段）
**段数**：1 段

{mode_hint}

{lang_hint}

{ref_rule}

**场景要求（重要，30 秒 = 一个精彩片段，通用规则，不限于任何题材）**：

**用户输入的主题，你要提取"一个场景的一个冲突点"**：
- 场景 = 一个地点 + 2~4 个角色 + 有冲突 + 有变化
- 只讲一个"冲突点"，不要讲完整故事
- **不要**只写"门口寒暄"、"两个人对话"这种简单场景
- **不要**硬编码任何具体地点，让 AI 根据题材自己决定

**30 秒分秒脚本结构（通用，不限于任何题材）**：
- 只生成 1 段，30 秒内讲完一个"冲突片段"，拆成 8~12 个镜头：
  - 0~6 秒（2 个镜头）：场景建立 + 人物出场（特写 + 中景）
  - 6~15 秒（3 个镜头）：冲突出现（正反打：A 嘲讽 → B 反应 → C 插话）
  - 15~22 秒（2~3 个镜头）：冲突升级（动作/道具特写，如名表、酒杯）
  - 22~28 秒（1~2 个镜头）：反转或高潮（B 反击，一句台词）
  - 28~30 秒（1 个镜头）：结尾钩子（全景，气氛定格）
- **每个镜头 2~4 秒**，必须有景别变化（特写/中景/全景交替）
- **不要试图讲完整故事**，只讲一个"精彩片段"

**核心规则**：

**1. 角色数量（由剧情决定，不硬限制）**：
- 角色数量由剧情需要决定：两人对话 → 2 个；同学聚会 → 6~10 个；宴席 → 10+ 个
- **但同一场景内，人数必须固定**：每个分秒脚本开头写明"本场景共 X 个人：A、B、C..."
- **不要在同一场景内增加或减少人物**（4.0 会自己加人，导致前后人数不一致）
- 群戏场景（聚会、宴席、会议）**必须把主要角色列全**，不要写"同学们"、"其他人"这种模糊描述
- 如果场景需要"群众演员"，明确写"背景虚化，不出现清晰的其他人物"
- 例（两人场景）：`本场景共 2 个人：[角色A]（[服装描述]）、[角色B]（[服装描述]）。`
- 例（群戏）：`本场景共 N 个人：[角色A]（[服装描述]）、[角色B]（[服装描述]）、[角色C]（[服装描述]）……（列全所有角色）。`

**角色命名要求（重要）**：
- 名字必须多样化，**避免**烂大街的高频名（如“小明、小红、小刚”这类泛称）
- 根据角色身份、年龄、背景，取有辨识度的名字
- 同一剧本里，名字不能重复

**2. 角色外观（appearance）**：
- **英文**，20-40 词
- 包含：人种 + 年龄 + 性别 + 发型 + 五官 + 体型 + 服装
- 例：`Asian, 38 years old, male, short black hair, sharp eyes, lean build, wearing simple cotton shirt`

**2.1 角色气质（vibe）**：
- **英文**，3-6 词
- 根据角色身份推断：
  - 富豪/董事长 → `wealthy, high-status, confident, authoritative`
  - 成功人士/精英 → `successful, elite, polished, sophisticated`
  - 白领/职场 → `professional, clean, modern, capable`
  - 学生/年轻人 → `youthful, fresh, natural, energetic`
  - 普通工人/小人物 → `ordinary, hardworking, sincere, modest`
  - 反派/势利眼 → `arrogant, flashy, condescending, smug`
- 例：`wealthy, high-status, confident, well-groomed`

**2.2 角色服装（outfit）**：
- **英文**，5-12 词
- 根据身份和场景推断：
  - 富豪/精英 → `bespoke tailored suit, premium fabric, crisp shirt, luxury watch`
  - 白领 → `minimalist business casual, high-quality cotton, clean lines`
  - 休闲 → `minimalist casual wear, premium denim, simple sneakers`
  - 礼服 → `elegant evening gown, refined details, luxury fabric`
  - 普通/穷 → `simple worn clothes, modest fabric, practical shoes`
- 例：`bespoke tailored suit, premium fabric, luxury watch`

**3. 分秒脚本（重要，核心规则）**：

**只有 1 段，30 秒讲一个"冲突片段"**：
- 30 秒内：建立（0~10 秒）→ 冲突（10~20 秒）→ 升级/反转（20~30 秒）
- **不要试图讲完整故事**，只讲一个片段
- **不要跳到下一个场景**
- 但**这个片段内部要有变化**（不是"站着说话 30 秒"）

**每个 `shot_prompt` 字段**：
- 格式：**分秒脚本**，每 2~4 秒一个镜头，共 8~12 个镜头
- 示例格式：
30秒分秒脚本，严格按时间点切镜头：
0~3秒：特写，[角色B]举红酒杯，嘴角冷笑，餐厅暖光。
3~6秒：切[角色A]中景，低头，手指摩挲杯沿，朴素衬衫。
6~9秒：[角色B]（嘲讽）："[角色A]啊，你还是这么穷酸。"
9~12秒：切[角色C]特写，皱眉，欲言又止。
12~15秒：[角色A]抬头，微笑，不说话。
15~18秒：全景，[其他角色]偷笑，气氛尴尬。
18~22秒：[角色A]抬手，手腕名表反光，特写。
22~25秒：[角色B]特写，脸色骤变，酒杯停在半空。
25~28秒：[角色A]（淡定）："这酒我从法国带的。"
28~30秒：全景，全场安静，只有酒杯轻碰声。
无字幕。

- **对白要写在分秒脚本里，不要只放在 `dialogue` 字段**
- **长度**：300~500 字（分秒脚本比流水账短，但信息密度高）
- **镜头数**：8~12 个（少于 8 个节奏慢，多于 12 个切太碎）
- **每镜时长**：2~4 秒（不要超过 4 秒，超过就慢）
- **必须有**：特写（表情/道具）、正反打（A 说 → B 反应）、全景（交代关系）
- **人物一致性（重要）**：分秒脚本里每个镜头出现的人物，必须和定妆照一致（面孔、发型、服装）。不要改变。例：`[角色A]（[服装描述]，同定妆照）`。

**3.1 段内连贯性（重要）**：
- 只有 1 段 30 秒，段内要有完整的小起承转合
- 按分秒脚本切 8~12 个镜头，镜头之间要连贯（同一场景、同一批人）
- 景别交替：特写 → 中景 → 全景，不要连续 3 个同景别

**3.2 剧情连贯性（重要）**：
- 只有 1 段 30 秒，是一个完整的"冲突片段"
- 段内时间连续，不要跳（不要"过了三天"、"与此同时"）
- 开头和结尾要在**同一场景、同一批人**

**3.5 情绪弧线（重要）**：
- 30 秒内要有小起伏：建立（平）→ 冲突（紧）→ 升级/反转（高潮）
- 结尾必须有"钩子"，让观众想看"下一集"

**3.6 声音时间轴（重要）**：
- 分秒脚本里要写清声音：
- 0~3 秒：环境声（餐厅碗筷声、低声交谈），无对白。
- 3~6 秒：[角色B]说"..."（嘲讽语气）。
- ...
- **不要前 5 秒静默**，从第 0 秒就有环境声。
- 结尾可以留 1~2 秒纯环境声（定格感）。

**4. 对话（类型自适应）**：

- 30 秒内 **6~10 句**对白
- 对话 **10~30 字**（**用 {lang_name}**）
- 每句 2~4 秒
- **每句对白必须包含 `tone`（语气）字段**
- tone 例：热情、冷漠、嘲讽、温柔、紧张、愤怒、平静
- **多角色对话时，必须明确角色名，不要写"有人说"、"他回答"**

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

{json_example}

**注意**：
- characters 数组必须有"所有角色"，每个角色必须有 `vibe` 和 `outfit`
- scenes 数组只有 1 个元素
- 每个 scene 必须有 `shot_prompt` 字段（分秒脚本，中文 300~500 字，无字幕）
- 每个 scene 必须有 `end_action` 字段（这一段的结尾动作）
- 每个 dialogue 必须有 `tone` 字段（语气）
- **所有剧情由你根据用户输入"自由生成"，不要套用任何"固定剧情"**
- **只有 1 段 30 秒，是一个精彩片段，不要推进到下一个场景**
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


    @staticmethod
    def convert_user_script_to_prompts(user_script: Dict) -> List[Dict]:
        """
        用户脚本模式：parse_user_script 已经输出流水账 shot_prompt（含 8~10 个镜头、无字幕、人物一致性），
        这里只做“兜底补缺”，不重复补
        """
        scenes = []
        for scene in user_script["scenes"]:
            shot_prompt = scene.get("shot_prompt", "").strip()

            # 兜底：如果 shot_prompt 为空，跳过
            if not shot_prompt:
                continue

            # 兜底：补"8~10 个镜头"（如果没写）
            if "个镜头" not in shot_prompt:
                shot_prompt = f"30秒智能分镜，8~10 个镜头。{shot_prompt}"

            # 兜底：补"无字幕"（如果没写）
            if "无字幕" not in shot_prompt:
                shot_prompt += "无字幕。"

            # 兜底：补"人物一致性"（如果没写）
            if "人物一致性" not in shot_prompt and "和定妆照一致" not in shot_prompt:
                shot_prompt += "所有人物面孔、发型、服装必须和定妆照一致。"

            scenes.append({
                "index": scene.get("index", 1),
                "shot_prompt": shot_prompt,
                "end_action": scene.get("end_action", ""),
                "characters_in_scene": scene.get("characters_in_scene", []),
                "dialogue": scene.get("dialogue", []),
            })
        return scenes

    @staticmethod
    async def parse_user_script(raw_text: str, language: str = "zh", reference_urls: List[str] = None) -> Dict:
        """
        用户脚本模式：
        1. 从用户剧本提取“一句话主题”（核心冲突 + 人物 + 场景）
        2. 把“一句话主题”传给 generate_script（< 50 字，走“一句话主题”分支，AI 自由发挥）
        3. 效果和 AI 生成模式（一句话主题）一样
        """
        reference_urls = reference_urls or []

        # ========== 参考图视觉分析 ==========
        reference_info = []
        if reference_urls:
            from app.services.reference_analyzer import reference_analyzer
            print(f"[SCRIPT] 分析 {len(reference_urls)} 张参考图...")
            try:
                reference_info = await reference_analyzer.analyze(reference_urls)
                print(f"[SCRIPT] 参考图分析完成: {len(reference_info)} 张")
            except Exception as e:
                print(f"[SCRIPT] 参考图分析失败（不影响主流程）: {e}")
                reference_info = []
        # ==================================

        # ========== 提取“一句话主题” ==========
        extract_prompt = f"""从下面用户剧本里，提取“一句话主题”。

**用户剧本**：
{raw_text}

**要求**：
- 一句话概括核心冲突（20~40 字）
- 保留核心人物和场景
- 不要超过 50 字
- 只输出一句话，不要解释

**示例**：
用户剧本：大夏将军守城断水，跪井祈祷，现代小伙听到，接水管放水，将军扔玉佩报答，小伙捞到古董。
一句话主题：古代将军守城断水跪井祈祷，现代小伙接水管放水，将军扔玉佩报答。
"""

        def _extract():
            resp = requests.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "qwen-max",
                    "messages": [{"role": "user", "content": extract_prompt}],
                    "temperature": 0.3,
                    "max_tokens": 200,
                },
                timeout=60,
            )
            if resp.status_code != 200:
                raise Exception(f"通义千问错误: {resp.status_code}")
            return resp.json()["choices"][0]["message"]["content"].strip()

        one_line_theme = await asyncio.to_thread(_extract)
        print(f"[SCRIPT] 提取一句话主题: {one_line_theme}")

        # 强制截断到 50 字以内（确保走“一句话主题”分支）
        if len(one_line_theme) > 50:
            one_line_theme = one_line_theme[:50]
        # ======================================

        # 调 generate_script（< 50 字，走“一句话主题”分支，AI 自由发挥）
        script = await ScriptGenerator.generate_script(
            theme=one_line_theme,
            duration=30,
            style="",
            reference_count=len(reference_urls),
            reference_info=reference_info,
            language=language,
            mode="real",
        )

        script["reference_urls"] = reference_urls
        return script

script_generator = ScriptGenerator()