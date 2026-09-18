"""
生成 6 个 A+ 模板的底图（PNG）和布局配置（JSON）
运行一次：py scripts/export_aplus_templates.py
生成到：app/data/aplus_templates/template_01/ ... template_06/
"""
import os
import json
from PIL import Image, ImageDraw, ImageFilter

# ========== 配置 ==========
OUTPUT_DIR = "app/data/aplus_templates"
CANVAS = (1464, 600)  # A+ 标准尺寸

# 科技感配色（会被运行时替换为产品主色）
TECH_COLORS = {
    "primary": (0, 200, 255),      # 青色
    "secondary": (100, 50, 200),   # 紫色
    "dark": (10, 15, 30),          # 深蓝黑
    "light": (240, 245, 255),      # 浅蓝白
    "text_dark": (20, 25, 45),
    "text_light": (255, 255, 255),
}


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def _hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip("#")
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))


# ========== 模板 1：左文右图 ==========
def template_01():
    w, h = CANVAS
    img = Image.new("RGB", (w, h), TECH_COLORS["light"])
    draw = ImageDraw.Draw(img)

    left_w = int(w * 0.42)

    # 左侧深色渐变区
    for y in range(h):
        ratio = y / h
        r = int(TECH_COLORS["dark"][0] * (1 - ratio) + 20 * ratio)
        g = int(TECH_COLORS["dark"][1] * (1 - ratio) + 25 * ratio)
        b = int(TECH_COLORS["dark"][2] * (1 - ratio) + 50 * ratio)
        draw.line([(0, y), (left_w, y)], fill=(r, g, b))

    # 装饰：左上角几何线条
    for i in range(5):
        offset = i * 30
        draw.line([(20, 20 + offset), (20 + offset, 20)], fill=TECH_COLORS["primary"], width=2)

    # 装饰：底部渐变色条
    for x in range(left_w):
        ratio = x / left_w
        r = int(TECH_COLORS["primary"][0] * (1 - ratio) + TECH_COLORS["secondary"][0] * ratio)
        g = int(TECH_COLORS["primary"][1] * (1 - ratio) + TECH_COLORS["secondary"][1] * ratio)
        b = int(TECH_COLORS["primary"][2] * (1 - ratio) + TECH_COLORS["secondary"][2] * ratio)
        draw.line([(x, h - 8), (x, h)], fill=(r, g, b))

    # 右侧图区留白（不带内容，AI 图会填进来）
    # 右侧加细边框
    draw.rectangle([left_w, 0, w - 1, h - 1], outline=TECH_COLORS["primary"], width=1)

    layout = {
        "canvas_size": [w, h],
        "placeholders": [
            {"type": "image", "name": "main_image", "x": left_w, "y": 0, "w": w - left_w, "h": h},
            {"type": "text", "name": "title", "x": 60, "y": 180, "max_w": left_w - 120,
             "font": "SourceHanSerif-Bold", "size": 56, "color": "#FFFFFF", "weight": "bold"},
            {"type": "text", "name": "subtitle", "x": 60, "y": 270, "max_w": left_w - 120,
             "font": "SourceHanSans", "size": 26, "color": "#B0C0D0"},
        ],
    }
    return img, layout


# ========== 模板 2：上文下图 ==========
def template_02():
    w, h = CANVAS
    img = Image.new("RGB", (w, h), TECH_COLORS["light"])
    draw = ImageDraw.Draw(img)

    top_h = int(h * 0.32)

    # 顶部深色渐变
    for y in range(top_h):
        ratio = y / top_h
        r = int(TECH_COLORS["dark"][0] * (1 - ratio) + 30 * ratio)
        g = int(TECH_COLORS["dark"][1] * (1 - ratio) + 35 * ratio)
        b = int(TECH_COLORS["dark"][2] * (1 - ratio) + 70 * ratio)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    # 装饰：右上角几何图形（菱形）
    cx, cy = w - 100, 60
    for i in range(3):
        size = 20 + i * 15
        draw.polygon([
            (cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)
        ], outline=TECH_COLORS["primary"])

    # 装饰：标题下渐变线
    for x in range(int(w * 0.15), int(w * 0.85)):
        ratio = (x - w * 0.15) / (w * 0.7)
        r = int(TECH_COLORS["primary"][0] * (1 - ratio) + TECH_COLORS["secondary"][0] * ratio)
        g = int(TECH_COLORS["primary"][1] * (1 - ratio) + TECH_COLORS["secondary"][1] * ratio)
        b = int(TECH_COLORS["primary"][2] * (1 - ratio) + TECH_COLORS["secondary"][2] * ratio)
        draw.line([(x, top_h - 5), (x, top_h)], fill=(r, g, b))

    layout = {
        "canvas_size": [w, h],
        "placeholders": [
            {"type": "image", "name": "main_image", "x": 0, "y": top_h, "w": w, "h": h - top_h},
            {"type": "text", "name": "title", "x": w // 2, "y": 70, "max_w": int(w * 0.8),
             "font": "SourceHanSerif-Bold", "size": 60, "color": "#FFFFFF", "anchor": "mm"},
            {"type": "text", "name": "subtitle", "x": w // 2, "y": 150, "max_w": int(w * 0.7),
             "font": "SourceHanSans", "size": 26, "color": "#C0D0E0", "anchor": "mm"},
        ],
    }
    return img, layout


# ========== 模板 3：三图并列 ==========
def template_03():
    w, h = CANVAS
    img = Image.new("RGB", (w, h), TECH_COLORS["dark"])
    draw = ImageDraw.Draw(img)

    top_h = int(h * 0.18)

    # 顶部细渐变条
    for x in range(w):
        ratio = x / w
        r = int(TECH_COLORS["primary"][0] * (1 - ratio) + TECH_COLORS["secondary"][0] * ratio)
        g = int(TECH_COLORS["primary"][1] * (1 - ratio) + TECH_COLORS["secondary"][1] * ratio)
        b = int(TECH_COLORS["primary"][2] * (1 - ratio) + TECH_COLORS["secondary"][2] * ratio)
        draw.line([(x, 0), (x, 4)], fill=(r, g, b))

    # 三图分隔线
    for i in range(1, 3):
        x = int(w * i / 3)
        draw.line([(x, top_h), (x, h)], fill=TECH_COLORS["primary"], width=2)

    layout = {
        "canvas_size": [w, h],
        "placeholders": [
            {"type": "image", "name": "image_1", "x": 0, "y": top_h, "w": w // 3 - 1, "h": h - top_h},
            {"type": "image", "name": "image_2", "x": w // 3 + 1, "y": top_h, "w": w // 3 - 2, "h": h - top_h},
            {"type": "image", "name": "image_3", "x": 2 * w // 3, "y": top_h, "w": w - 2 * w // 3, "h": h - top_h},
            {"type": "text", "name": "title", "x": w // 2, "y": top_h // 2, "max_w": int(w * 0.9),
             "font": "SourceHanSerif-Bold", "size": 48, "color": "#FFFFFF", "anchor": "mm"},
        ],
    }
    return img, layout


# ========== 模板 4：左 3 特写 + 右大场景 ==========
def template_04():
    w, h = CANVAS
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 左侧特写区（占 28% 宽）
    left_w = int(w * 0.28)

    # 左侧浅色背景
    draw.rectangle([0, 0, left_w, h], fill=(248, 248, 250))

    # 三条细分隔线（把左侧分成 3 块）
    block_h = h // 3
    for i in range(1, 3):
        y = i * block_h
        draw.line([(20, y), (left_w - 20, y)], fill=(220, 220, 225), width=1)

    # 右侧场景区边框（细边框）
    draw.rectangle([left_w, 0, w - 1, h - 1], outline=(220, 220, 225), width=1)

    # 左侧顶部装饰：渐变色块
    for y in range(0, 8):
        ratio = y / 8
        r = int(TECH_COLORS["primary"][0] * (1 - ratio) + TECH_COLORS["secondary"][0] * ratio)
        g = int(TECH_COLORS["primary"][1] * (1 - ratio) + TECH_COLORS["secondary"][1] * ratio)
        b = int(TECH_COLORS["primary"][2] * (1 - ratio) + TECH_COLORS["secondary"][2] * ratio)
        draw.line([(0, y), (left_w, y)], fill=(r, g, b))

    layout = {
        "canvas_size": [w, h],
        "placeholders": [
            # 左侧 3 张特写图
            {"type": "image", "name": "closeup_1", "x": 20, "y": 30, "w": left_w - 40, "h": block_h - 50},
            {"type": "image", "name": "closeup_2", "x": 20, "y": block_h + 30, "w": left_w - 40, "h": block_h - 50},
            {"type": "image", "name": "closeup_3", "x": 20, "y": block_h * 2 + 30, "w": left_w - 40, "h": block_h - 60},
            # 右侧 1 张大场景图
            {"type": "image", "name": "scene_image", "x": left_w + 10, "y": 10, "w": w - left_w - 20, "h": h - 20},
        ],
    }
    return img, layout


# ========== 模板 5：双场景对比 ==========
def template_05():
    w, h = CANVAS
    img = Image.new("RGB", (w, h), TECH_COLORS["dark"])
    draw = ImageDraw.Draw(img)

    # 中央斜线分割
    mid_x = w // 2
    # 左半区深色
    draw.rectangle([0, 0, mid_x - 4, h], fill=(15, 20, 40))
    # 右半区略浅
    draw.rectangle([mid_x + 4, 0, w, h], fill=(20, 30, 55))

    # 中央斜线装饰
    for i in range(-h, w, 40):
        draw.line([(mid_x - 4 + i, 0), (mid_x - 4 + i + h, h)],
                  fill=(40, 60, 100), width=1)

    # 顶部标题区
    top_h = int(h * 0.15)
    for x in range(w):
        ratio = x / w
        r = int(TECH_COLORS["primary"][0] * (1 - ratio) + TECH_COLORS["secondary"][0] * ratio)
        g = int(TECH_COLORS["primary"][1] * (1 - ratio) + TECH_COLORS["secondary"][1] * ratio)
        b = int(TECH_COLORS["primary"][2] * (1 - ratio) + TECH_COLORS["secondary"][2] * ratio)
        draw.line([(x, top_h - 3), (x, top_h)], fill=(r, g, b))

    # 底部标签栏
    label_bar_h = int(h * 0.12)
    label_bar_y = h - label_bar_h
    draw.rectangle([0, label_bar_y, mid_x - 4, h], fill=(10, 15, 30))
    draw.rectangle([mid_x + 4, label_bar_y, w, h], fill=(30, 50, 90))

    layout = {
        "canvas_size": [w, h],
        "placeholders": [
            {"type": "image", "name": "image_left", "x": 0, "y": top_h, "w": mid_x - 4, "h": h - top_h - label_bar_h},
            {"type": "image", "name": "image_right", "x": mid_x + 4, "y": top_h, "w": w - mid_x - 4, "h": h - top_h - label_bar_h},
            {"type": "text", "name": "title", "x": w // 2, "y": top_h // 2, "max_w": int(w * 0.8),
             "font": "SourceHanSerif-Bold", "size": 42, "color": "#FFFFFF", "anchor": "mm"},
            {"type": "text", "name": "label_left", "x": (mid_x - 4) // 2, "y": label_bar_y + label_bar_h // 2,
             "max_w": mid_x - 60, "font": "SourceHanSans", "size": 24, "color": "#FFFFFF", "anchor": "mm"},
            {"type": "text", "name": "label_right", "x": mid_x + 4 + (w - mid_x - 4) // 2, "y": label_bar_y + label_bar_h // 2,
             "max_w": w - mid_x - 60, "font": "SourceHanSans", "size": 24, "color": "#FFFFFF", "anchor": "mm"},
        ],
    }
    return img, layout


# ========== 模板 6：左 2 图 + 右文字 ==========
def template_06():
    w, h = CANVAS
    img = Image.new("RGB", (w, h), TECH_COLORS["dark"])
    draw = ImageDraw.Draw(img)

    # 全屏深色背景
    draw.rectangle([0, 0, w, h], fill=(20, 25, 40))

    # 左侧两图边框（占 65% 宽）
    draw.rectangle([20, 20, 20 + 950, 20 + 270], outline=TECH_COLORS["primary"], width=1)
    draw.rectangle([20, 310, 20 + 950, 310 + 270], outline=TECH_COLORS["primary"], width=1)

    # 右侧文字区装饰线
    draw.rectangle([1000, 100, 1000 + 80, 103], fill=TECH_COLORS["primary"])
    draw.rectangle([1000, 103, 1000 + 160, 106], fill=TECH_COLORS["secondary"])
    draw.rectangle([1000, 500, 1000 + 50, 502], fill=TECH_COLORS["primary"])

    layout = {
        "canvas_size": [w, h],
        "placeholders": [
            {"type": "image", "name": "image_top", "x": 20, "y": 20, "w": 950, "h": 270},
            {"type": "image", "name": "image_bottom", "x": 20, "y": 310, "w": 950, "h": 270},
            {"type": "text", "name": "label_top", "x": 30, "y": -5, "max_w": 400,
             "font": "SourceHanSans", "size": 16, "color": "#00C8FF"},
            {"type": "text", "name": "label_bottom", "x": 30, "y": 285, "max_w": 400,
             "font": "SourceHanSans", "size": 16, "color": "#00C8FF"},
            {"type": "text", "name": "title", "x": 1000, "y": 140, "max_w": 440,
             "font": "SourceHanSerif-Bold", "size": 36, "color": "#FFFFFF"},
            {"type": "text", "name": "subtitle", "x": 1000, "y": 220, "max_w": 440,
             "font": "SourceHanSans", "size": 20, "color": "#B0C0D0"},
            {"type": "text", "name": "body", "x": 1000, "y": 320, "max_w": 440,
             "font": "SourceHanSans", "size": 15, "color": "#8090A0"},
        ],
    }
    return img, layout


# ========== 主流程 ==========
def main():
    templates = [
        ("template_01", template_01),
        ("template_02", template_02),
        ("template_03", template_03),
        ("template_04", template_04),
        ("template_05", template_05),
        ("template_06", template_06),
    ]
    for name, fn in templates:
        tpl_dir = os.path.join(OUTPUT_DIR, name)
        _ensure_dir(tpl_dir)
        img, layout = fn()
        img.save(os.path.join(tpl_dir, "background.png"))
        with open(os.path.join(tpl_dir, "layout.json"), "w", encoding="utf-8") as f:
            json.dump(layout, f, ensure_ascii=False, indent=2)
        print(f"[OK] {name}")

    print(f"\n全部完成，输出到：{OUTPUT_DIR}")


if __name__ == "__main__":
    main()