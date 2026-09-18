"""
图文合成服务 - PIL 处理（含 AI 标识 + 隐式标识）
"""
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from typing import Optional, List, Tuple


class ImageComposer:
    """图文合成器"""
    
    FONT_PATH = "app/data/fonts/SourceHanSans.ttf"
    
    @staticmethod
    def _load_image(image_url: str) -> Image.Image:
        resp = requests.get(image_url, timeout=30)
        return Image.open(BytesIO(resp.content)).convert("RGB")
    
    @staticmethod
    def _get_font(size: int):
        try:
            return ImageFont.truetype(ImageComposer.FONT_PATH, size=size)
        except:
            return ImageFont.load_default()
    
    @staticmethod
    def _fit_text(text: str, max_width: int, max_size: int, min_size: int = 16):
        """
        自动缩小字体，使文字宽度 <= max_width
        返回：(font, actual_width)
        """
        size = max_size
        while size > min_size:
            font = ImageComposer._get_font(size)
            # 用临时 draw 计算宽度
            tmp_img = Image.new("RGB", (10, 10))
            tmp_draw = ImageDraw.Draw(tmp_img)
            bbox = tmp_draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            if text_w <= max_width:
                return font, text_w
            size -= 2
        
        # 到最小字号还放不下，截断
        font = ImageComposer._get_font(min_size)
        tmp_img = Image.new("RGB", (10, 10))
        tmp_draw = ImageDraw.Draw(tmp_img)
        
        truncated = text
        while len(truncated) > 1:
            bbox = tmp_draw.textbbox((0, 0), truncated + "…", font=font)
            if bbox[2] - bbox[0] <= max_width:
                break
            truncated = truncated[:-1]
        
        final_text = truncated + "…" if truncated != text else text
        bbox = tmp_draw.textbbox((0, 0), final_text, font=font)
        return font, bbox[2] - bbox[0]

    @staticmethod
    def add_ai_watermark(image_bytes: bytes) -> bytes:
        """在图片右下角添加"AI生成"水印"""
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        width, height = img.size
        draw = ImageDraw.Draw(img)
        
        font_size = max(20, int(width * 0.03))
        font = ImageComposer._get_font(font_size)
        
        text = "AI生成"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        x = width - text_w - 20
        y = height - text_h - 20
        
        padding = 8
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle(
            [x - padding, y - padding, x + text_w + padding, y + text_h + padding],
            fill=(0, 0, 0, 120)
        )
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)
        draw.text((x, y), text, font=font, fill=(255, 255, 255))
        
        output = BytesIO()
        img.save(output, format="JPEG", quality=95)
        return output.getvalue()
    
    @staticmethod
    def add_ai_metadata(image_bytes: bytes) -> bytes:
        """在 EXIF 中写入 AI 生成标识"""
        img = Image.open(BytesIO(image_bytes))
        exif = img.getexif()
        exif[0x010E] = "AI-Generated Image"  # ImageDescription
        exif[0x0131] = "Lingjing AI"          # Software
        exif[0x010F] = "Lingjing AI"          # Make
        
        output = BytesIO()
        img.save(output, format="JPEG", quality=95, exif=exif)
        return output.getvalue()
    
    @staticmethod
    def add_selling_point_text(
        image_url: str,
        title: str,
        subtitle: str = "",
        position: str = "top-left",
    ) -> Optional[bytes]:
        """在图片上添加卖点文字"""
        try:
            img = ImageComposer._load_image(image_url)
            width, height = img.size
            draw = ImageDraw.Draw(img)
            
            title_size = int(height * 0.08)
            subtitle_size = int(height * 0.04)
            title_font = ImageComposer._get_font(title_size)
            subtitle_font = ImageComposer._get_font(subtitle_size)
            
            padding = int(width * 0.05)
            
            if position == "top-left":
                title_x, title_y = padding, padding
            elif position == "top-center":
                title_x, title_y = width // 2, padding
            elif position == "bottom-left":
                title_x, title_y = padding, height - int(height * 0.2)
            else:
                title_x, title_y = width // 2, height - int(height * 0.2)
            
            anchor = "la" if "left" in position else "ma"
            
            title_bbox = draw.textbbox((title_x, title_y), title, font=title_font, anchor=anchor)
            bg_padding = 20
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rectangle(
                [title_bbox[0] - bg_padding, title_bbox[1] - bg_padding,
                 title_bbox[2] + bg_padding, title_bbox[3] + bg_padding],
                fill=(0, 0, 0, 100)
            )
            img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
            draw = ImageDraw.Draw(img)
            draw.text((title_x, title_y), title, font=title_font, fill=(255, 255, 255), anchor=anchor)
            
            if subtitle:
                subtitle_y = title_y + title_size + 10
                draw.text((title_x, subtitle_y), subtitle, font=subtitle_font, fill=(240, 240, 240), anchor=anchor)
            
            output = BytesIO()
            img.save(output, format="JPEG", quality=95)
            return output.getvalue()
        
        except Exception as e:
            print(f"[COMPOSER] 文字合成失败: {e}")
            return None
    
    @staticmethod
    def create_aplus_image(
        main_image_url: str,
        small_image_urls: List[str],
        title: str,
        subtitle: str = "",
        canvas_size: Tuple[int, int] = (1464, 600),
    ) -> Optional[bytes]:
        """创建 A+ 图（多图拼接）"""
        try:
            canvas_w, canvas_h = canvas_size
            canvas = Image.new("RGB", (canvas_w, canvas_h), (245, 245, 245))
            draw = ImageDraw.Draw(canvas)
            
            # 标题栏
            title_bar_h = int(canvas_h * 0.15)
            draw.rectangle([0, 0, canvas_w, title_bar_h], fill=(100, 150, 200))
            
            title_size = int(title_bar_h * 0.5)
            subtitle_size = int(title_bar_h * 0.25)
            title_font = ImageComposer._get_font(title_size)
            subtitle_font = ImageComposer._get_font(subtitle_size)
            
            draw.text((canvas_w // 2, int(title_bar_h * 0.4)), title, 
                     font=title_font, fill=(255, 255, 255), anchor="mm")
            if subtitle:
                draw.text((canvas_w // 2, int(title_bar_h * 0.75)), subtitle,
                         font=subtitle_font, fill=(230, 230, 230), anchor="mm")
            
            # 内容区
            content_y = title_bar_h
            content_h = canvas_h - title_bar_h
            
            # 左侧大图
            main_w = int(canvas_w * 0.6)
            main_img = ImageComposer._load_image(main_image_url)
            main_img = main_img.resize((main_w, content_h), Image.LANCZOS)
            canvas.paste(main_img, (0, content_y))
            
            # 右侧小图
            small_w = canvas_w - main_w
            if small_image_urls:
                small_h = content_h // len(small_image_urls)
                for i, url in enumerate(small_image_urls[:3]):
                    small_img = ImageComposer._load_image(url)
                    small_img = small_img.resize((small_w, small_h), Image.LANCZOS)
                    canvas.paste(small_img, (main_w, content_y + i * small_h))
            
            output = BytesIO()
            canvas.save(output, format="JPEG", quality=95)
            return output.getvalue()
        
        except Exception as e:
            print(f"[COMPOSER] A+图合成失败: {e}")
            return None
    
    @staticmethod
    def force_white_background(image_url: str) -> Optional[bytes]:
        """强制纯白背景"""
        import numpy as np
        try:
            img = ImageComposer._load_image(image_url)
            arr = np.array(img)
            mask = (arr[:, :, 0] > 230) & (arr[:, :, 1] > 230) & (arr[:, :, 2] > 230)
            arr[mask] = [255, 255, 255]
            img = Image.fromarray(arr)
            output = BytesIO()
            img.save(output, format="JPEG", quality=95)
            return output.getvalue()
        except Exception as e:
            print(f"[COMPOSER] 白底处理失败: {e}")
            return None

    @staticmethod
    def _draw_text_with_bg(img, draw, pos, text, font, text_color,
                            padding=18, bg_alpha=150, anchor=None):
        """
        在文字下面加半透明黑色底色条，保证任何背景下都清晰可读。
        返回更新后的 (img, draw)。
        """
        bbox = draw.textbbox(pos, text, font=font, anchor=anchor)
        bar_left = bbox[0] - padding
        bar_top = bbox[1] - padding // 2
        bar_right = bbox[2] + padding
        bar_bottom = bbox[3] + padding // 2

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle(
            [bar_left, bar_top, bar_right, bar_bottom],
            fill=(0, 0, 0, bg_alpha)
        )
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)
        draw.text(pos, text, font=font, fill=text_color, anchor=anchor)
        return img, draw

    @staticmethod
    def add_scene_text_with_template(
        image_url: str,
        title: str,
        subtitle: str = "",
        template_idx: int = 0,
    ) -> Optional[bytes]:
        """场景图文字（所有模板都带半透明底色，保证可读）"""
        try:
            img = ImageComposer._load_image(image_url)
            width, height = img.size

            # 判断背景明暗
            img_small = img.resize((50, 50))
            pixels = list(img_small.getdata())
            avg = sum((p[0] + p[1] + p[2]) / 3 for p in pixels) / len(pixels)
            is_dark_bg = avg < 128

            text_color = (255, 255, 255)
            sub_color = (240, 240, 240)

            padding = max(int(width * 0.06), 40)
            max_text_w = width - padding * 2

            draw = ImageDraw.Draw(img)

            # 标题自适应
            title_max_size = int(height * 0.09)
            title_font, title_w = ImageComposer._fit_text(
                title, max_text_w, title_max_size, min_size=24
            )

            # 副标题自适应
            sub_font, sub_w = None, 0
            if subtitle:
                sub_max_size = int(height * 0.035)
                sub_font, sub_w = ImageComposer._fit_text(
                    subtitle, int(max_text_w * 0.9), sub_max_size, min_size=14
                )

            title_bbox = draw.textbbox((0, 0), title, font=title_font)
            title_h = title_bbox[3] - title_bbox[1]

            # ========== 模板0：左上 ==========
            if template_idx == 0:
                title_x = padding
                title_y = padding
                img, draw = ImageComposer._draw_text_with_bg(
                    img, draw, (title_x, title_y), title, title_font, text_color
                )
                if subtitle and sub_font:
                    img, draw = ImageComposer._draw_text_with_bg(
                        img, draw, (title_x, title_y + title_h + 15),
                        subtitle, sub_font, sub_color
                    )

            # ========== 模板1：左下 ==========
            elif template_idx == 1:
                title_x = padding
                title_y = height - int(height * 0.28)
                img, draw = ImageComposer._draw_text_with_bg(
                    img, draw, (title_x, title_y), title, title_font, text_color
                )
                if subtitle and sub_font:
                    img, draw = ImageComposer._draw_text_with_bg(
                        img, draw, (title_x, title_y + title_h + 15),
                        subtitle, sub_font, sub_color
                    )

            # ========== 模板2：中上居中 ==========
            elif template_idx == 2:
                title_x = (width - title_w) // 2
                title_y = int(height * 0.12)
                img, draw = ImageComposer._draw_text_with_bg(
                    img, draw, (title_x, title_y), title, title_font, text_color
                )
                if subtitle and sub_font:
                    sub_x = (width - sub_w) // 2
                    img, draw = ImageComposer._draw_text_with_bg(
                        img, draw, (sub_x, title_y + title_h + 15),
                        subtitle, sub_font, sub_color
                    )

            # ========== 模板3：右上 ==========
            elif template_idx == 3:
                title_x = width - title_w - padding
                title_y = padding
                img, draw = ImageComposer._draw_text_with_bg(
                    img, draw, (title_x, title_y), title, title_font, text_color
                )
                if subtitle and sub_font:
                    sub_x = width - sub_w - padding
                    img, draw = ImageComposer._draw_text_with_bg(
                        img, draw, (sub_x, title_y + title_h + 10),
                        subtitle, sub_font, sub_color
                    )

            # ========== 模板4：底部色块居中 ==========
            elif template_idx == 4:
                bar_h = max(int(height * 0.22), title_h + (sub_font.size if sub_font else 0) + 60)
                bar_y = height - bar_h

                bar_color = (30, 40, 60)
                overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)
                overlay_draw.rectangle(
                    [0, bar_y, width, height],
                    fill=(0, 0, 0, 170)
                )
                img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
                draw = ImageDraw.Draw(img)

                title_x = (width - title_w) // 2
                title_y = bar_y + int(bar_h * 0.18)
                draw.text((title_x, title_y), title, font=title_font, fill=(255, 255, 255))

                if subtitle and sub_font:
                    sub_x = (width - sub_w) // 2
                    draw.text(
                        (sub_x, title_y + title_h + 15),
                        subtitle, font=sub_font,
                        fill=(230, 230, 240)
                    )

            output = BytesIO()
            img.save(output, format="JPEG", quality=95)
            return output.getvalue()

        except Exception as e:
            print(f"[COMPOSER] 场景图文字合成失败: {e}")
            import traceback
            traceback.print_exc()
            return None

image_composer = ImageComposer()