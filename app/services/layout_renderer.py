"""
按 AI 输出的布局 JSON 渲染图片
"""
import os
import requests
from io import BytesIO
from typing import Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont


class LayoutRenderer:
    FONT_DIR = "app/data/fonts"

    @staticmethod
    async def render_layout(
        canvas_size: List[int],
        elements: List[Dict],
        image_urls: Dict[str, str],
    ) -> Optional[bytes]:
        """
        按 elements 渲染一张图
        - canvas_size: [w, h]
        - elements: AI 输出的元素列表
        - image_urls: {name: url}，AI 生成的图，按 name 索引
        """
        try:
            w, h = canvas_size
            canvas = Image.new("RGBA", (w, h), (30, 30, 40, 255))

            for el in elements:
                el_type = el.get("type", "")
                if el_type == "image":
                    LayoutRenderer._draw_image(canvas, el, image_urls)
                elif el_type == "text":
                    LayoutRenderer._draw_text(canvas, el)
                elif el_type == "card":
                    LayoutRenderer._draw_card(canvas, el)

            out = BytesIO()
            canvas.convert("RGB").save(out, format="JPEG", quality=95)
            return out.getvalue()
        except Exception as e:
            print(f"[LAYOUT] 渲染失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def _draw_image(canvas, el, image_urls):
        name = el.get("name", "")
        url = image_urls.get(name, "")
        if not url:
            return
        try:
            resp = requests.get(url, timeout=60)
            img = Image.open(BytesIO(resp.content)).convert("RGBA")
            x, y = el.get("x", 0), el.get("y", 0)
            w, h = el.get("w", 100), el.get("h", 100)
            fit = el.get("fit", "cover")
            if fit == "cover":
                img = LayoutRenderer._fit_cover(img, w, h)
            else:
                img = LayoutRenderer._fit_contain(img, w, h)
            canvas.paste(img, (x, y), img)
        except Exception as e:
            print(f"[LAYOUT] 图 {name} 失败: {e}")

    @staticmethod
    def _draw_text(canvas, el):
        text = el.get("text", "")
        if not text:
            return
        x, y = el.get("x", 0), el.get("y", 0)
        font_name = el.get("font", "SourceHanSans")
        size = el.get("size", 24)
        color = el.get("color", "#FFFFFF")
        max_lines = el.get("maxLines", 3)
        max_w = el.get("max_w", canvas.width - x - 20)

        try:
            # ★ 先试 .ttf，再试 .otf，最后兜底
            font_path = None
            for ext in (".ttf", ".otf"):
                candidate = os.path.join(LayoutRenderer.FONT_DIR, f"{font_name}{ext}")
                if os.path.exists(candidate):
                    font_path = candidate
                    break
            if not font_path:
                font_path = os.path.join(LayoutRenderer.FONT_DIR, "SourceHanSans.ttf")
            font = ImageFont.truetype(font_path, size)
        except Exception:
            font = ImageFont.load_default()

        draw = ImageDraw.Draw(canvas)
        lines = LayoutRenderer._wrap_text(text, font, max_w, max_lines)
        line_height = int(size * 1.3)
        for i, line in enumerate(lines):
            draw.text((x, y + i * line_height), line, font=font, fill=color)

    @staticmethod
    def _draw_card(canvas, el):
        x, y = el.get("x", 0), el.get("y", 0)
        w, h = el.get("w", 100), el.get("h", 100)
        fill = el.get("fill", "rgba(0,0,0,0.5)")
        radius = el.get("borderRadius", 0)
        draw = ImageDraw.Draw(canvas, "RGBA")
        if radius > 0:
            draw.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=fill)
        else:
            draw.rectangle([x, y, x + w, y + h], fill=fill)

    @staticmethod
    def _fit_cover(img, w, h):
        iw, ih = img.size
        scale = max(w / iw, h / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        img = img.resize((nw, nh), Image.LANCZOS)
        left = (nw - w) // 2
        top = (nh - h) // 2
        return img.crop((left, top, left + w, top + h))

    @staticmethod
    def _fit_contain(img, w, h):
        iw, ih = img.size
        scale = min(w / iw, h / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        return img.resize((nw, nh), Image.LANCZOS)

    @staticmethod
    def _wrap_text(text, font, max_w, max_lines):
        lines = []
        current = ""
        for ch in text:
            test = current + ch
            bbox = font.getbbox(test)
            if bbox[2] - bbox[0] > max_w:
                lines.append(current)
                current = ch
                if len(lines) >= max_lines:
                    break
            else:
                current = test
        if current and len(lines) < max_lines:
            lines.append(current)
        return lines


layout_renderer = LayoutRenderer()