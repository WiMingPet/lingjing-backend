"""
A+ 图渲染器：读设计师模板（PNG + JSON），填 AI 内容
"""
import os
import json
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from typing import Dict, Optional


class AplusRenderer:
    """A+ 图渲染器"""

    TEMPLATE_DIR = "app/data/aplus_templates"
    FONT_DIR = "app/data/fonts"

    @staticmethod
    def render(template_name: str, contents: Dict, product_color: str = "") -> Optional[bytes]:
        """
        template_name: "template_01" ... "template_06"
        contents: {
            "main_image": "url",
            "image_1": "url", "image_2": "url", "image_3": "url",
            "image_left": "url", "image_right": "url",
            "title": "...", "subtitle": "...",
            "stat_1_label": "...", "stat_1_value": "...",
            ...
        }
        product_color: 产品主色（hex 或中文名），用于动态配色
        """
        try:
            tpl_dir = os.path.join(AplusRenderer.TEMPLATE_DIR, template_name)
            layout_path = os.path.join(tpl_dir, "layout.json")
            bg_path = os.path.join(tpl_dir, "background.png")

            if not os.path.exists(layout_path):
                print(f"[APLUS] 模板不存在: {template_name}")
                return None

            with open(layout_path, "r", encoding="utf-8") as f:
                layout = json.load(f)

            w, h = layout["canvas_size"]
            canvas = Image.open(bg_path).convert("RGBA")
            canvas = canvas.resize((w, h), Image.LANCZOS)

            # 动态配色：把底图的青色系替换为产品主色
            if product_color:
                canvas = AplusRenderer._apply_product_color(canvas, product_color)

            for ph in layout["placeholders"]:
                if ph["type"] == "image":
                    AplusRenderer._fill_image(canvas, ph, contents.get(ph["name"]))
                elif ph["type"] == "text":
                    AplusRenderer._fill_text(canvas, ph, contents.get(ph["name"], ""))

            output = BytesIO()
            canvas.convert("RGB").save(output, format="JPEG", quality=95)
            return output.getvalue()

        except Exception as e:
            print(f"[APLUS] 渲染失败 {template_name}: {e}")
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def _apply_product_color(canvas: Image.Image, product_color: str) -> Image.Image:
        """把底图的青色系替换为产品主色（简单色相映射）"""
        # 中文主色 → RGB
        color_map = {
            "金色": (200, 160, 60), "gold": (200, 160, 60),
            "黑色": (40, 40, 40), "black": (40, 40, 40),
            "白色": (240, 240, 240), "white": (240, 240, 240),
            "红色": (200, 60, 60), "red": (200, 60, 60),
            "蓝色": (60, 100, 200), "blue": (60, 100, 200),
            "绿色": (60, 160, 80), "green": (60, 160, 80),
            "紫色": (140, 80, 200), "purple": (140, 80, 200),
            "粉色": (220, 120, 160), "pink": (220, 120, 160),
            "橙色": (220, 130, 50), "orange": (220, 130, 50),
            "棕色": (140, 90, 50), "brown": (140, 90, 50),
            "灰色": (120, 120, 120), "gray": (120, 120, 120),
            "银色": (180, 180, 190), "silver": (180, 180, 190),
        }
        target = color_map.get(product_color.lower() if isinstance(product_color, str) else "",
                               color_map.get(product_color, None))

        if not target:
            return canvas

        # 简单做法：整体色相偏移（保留明暗关系）
        # 这里用简单方案：叠加一层半透明的主色
        overlay = Image.new("RGBA", canvas.size, target + (30,))
        return Image.alpha_composite(canvas, overlay)

    @staticmethod
    def _fill_image(canvas: Image.Image, ph: dict, image_source):
        if not image_source:
            return
        try:
            if isinstance(image_source, str):
                resp = requests.get(image_source, timeout=30)
                img = Image.open(BytesIO(resp.content)).convert("RGBA")
            else:
                img = image_source

            # 按 contain 方式缩放（完整显示图片，留白填充）
            target_w, target_h = ph["w"], ph["h"]
            img_ratio = img.width / img.height
            target_ratio = target_w / target_h

            if img_ratio > target_ratio:
                # 图片更宽，按宽度缩放
                new_w = target_w
                new_h = int(target_w / img_ratio)
            else:
                # 图片更高，按高度缩放
                new_h = target_h
                new_w = int(target_h * img_ratio)

            img = img.resize((new_w, new_h), Image.LANCZOS)

            # 居中显示（留白）
            paste_x = ph["x"] + (target_w - new_w) // 2
            paste_y = ph["y"] + (target_h - new_h) // 2

            # 用背景色填充占位区，再贴图
            bg_color = (20, 25, 40)  # 深色背景
            canvas.paste(bg_color, (ph["x"], ph["y"], ph["x"] + target_w, ph["y"] + target_h))
            canvas.paste(img, (paste_x, paste_y), img)
        except Exception as e:
            print(f"[APLUS] 填图失败 {ph['name']}: {e}")

    @staticmethod
    def _fill_text(canvas: Image.Image, ph: dict, text: str):
        if not text:
            return

        # ← 在 try 之前定义，避免 NameError
        font_path = None
        font = None

        try:
            font_name = ph.get("font", "SourceHanSans")
            font_path_ttf = os.path.join(AplusRenderer.FONT_DIR, f"{font_name}.ttf")
            font_path_otf = os.path.join(AplusRenderer.FONT_DIR, f"{font_name}.otf")

            if os.path.exists(font_path_ttf):
                font_path = font_path_ttf
                font = ImageFont.truetype(font_path_ttf, ph["size"])
            elif os.path.exists(font_path_otf):
                font_path = font_path_otf
                font = ImageFont.truetype(font_path_otf, ph["size"])
            else:
                print(f"[APLUS] 字体不存在: {font_name}")
        except Exception as e:
            print(f"[APLUS] 字体加载失败: {e}")

        if font is None:
            font = ImageFont.load_default()

        draw = ImageDraw.Draw(canvas)
        color_str = ph.get("color", "#FFFFFF")
        color = tuple(int(color_str.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))

        anchor = ph.get("anchor", "la")
        max_w = ph.get("max_w", 1000)
        text, font = AplusRenderer._truncate(draw, text, font, max_w, font_path=font_path)

        # ========== 如果有 bg_alpha 参数，画半透明底色 ==========
        if ph.get("bg_alpha"):
            bbox = draw.textbbox((ph["x"], ph["y"]), text, font=font, anchor=anchor)
            padding = ph.get("bg_padding", 15)
            bar_left = bbox[0] - padding
            bar_top = bbox[1] - padding // 2
            bar_right = bbox[2] + padding
            bar_bottom = bbox[3] + padding // 2

            overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rectangle(
                [bar_left, bar_top, bar_right, bar_bottom],
                fill=(0, 0, 0, ph["bg_alpha"])
            )
            canvas_rgba = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
            # ← 直接改 canvas 的像素，而不是 paste
            canvas.paste(canvas_rgba, (0, 0))
            draw = ImageDraw.Draw(canvas)

        draw.text((ph["x"], ph["y"]), text, font=font, fill=color, anchor=anchor)

    @staticmethod
    def _truncate(draw, text, font, max_w, font_path=None, min_size=14):
        """
        先尝试缩小字体，缩到 min_size 还放不下才截断
        返回 (text, font)
        """
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_w:
            return text, font

        if font_path:
            original_size = getattr(font, "size", 48)
            current_size = original_size
            while current_size > min_size:
                current_size -= 2
                try:
                    smaller_font = ImageFont.truetype(font_path, current_size)
                except Exception:
                    break
                bbox = draw.textbbox((0, 0), text, font=smaller_font)
                if bbox[2] - bbox[0] <= max_w:
                    return text, smaller_font

        # 缩到最小还放不下，才截断
        while len(text) > 1:
            text = text[:-1]
            bbox = draw.textbbox((0, 0), text + "…", font=font)
            if bbox[2] - bbox[0] <= max_w:
                return text + "…", font
        return text, font


aplus_renderer = AplusRenderer()