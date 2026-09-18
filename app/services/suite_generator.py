"""
套图生成服务（含 AI 标识 + 隐式标识）
"""
import requests
from typing import Dict, List
from app.services.kling import kling_service
from app.services.image_composer import image_composer
from app.services.oss_service import oss_service
from app.services.matting_service import matting_service
from app.services.aplus_renderer import aplus_renderer
from app.config import settings
class SuiteGenerator:
    """套图生成器"""
    
    @staticmethod
    async def _process_and_upload(image_url: str, sub_folder: str) -> str:
        """下载图片 → 加 AI 水印 → 加 EXIF → 上传 OSS"""
        try:
            resp = requests.get(image_url, timeout=60)
            img_bytes = resp.content
            
            # AI 水印
            img_bytes = image_composer.add_ai_watermark(img_bytes)
            # 隐式标识
            img_bytes = image_composer.add_ai_metadata(img_bytes)
            
            oss_url = await oss_service.upload_file(img_bytes, "jpg", sub_folder)
            return oss_url
        except Exception as e:
            print(f"[SUITE] 处理上传失败: {e}")
            return image_url
    
    @staticmethod
    async def generate_white_bg(cloth_url: str) -> List[dict]:
        """白底图：抠图 + 纯白背景合成（产品100%原貌，无阴影）"""
        import asyncio
        from PIL import Image
        from io import BytesIO

        try:
            product_png = await matting_service.segment_commodity(cloth_url)
            if not product_png:
                print("[SUITE] 白底图抠图失败")
                return []

            def _compose():
                product = Image.open(BytesIO(product_png)).convert("RGBA")
                pw, ph = product.size
                canvas_w = int(pw * 1.4)
                canvas_h = int(ph * 1.4)
                canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
                x = (canvas_w - pw) // 2
                y = (canvas_h - ph) // 2
                canvas.paste(product, (x, y), product)
                output = BytesIO()
                canvas.save(output, format="JPEG", quality=95)
                return output.getvalue()

            img_bytes = await asyncio.to_thread(_compose)
            if not img_bytes:
                return []

            # 存无水印版
            clean_url = await oss_service.upload_file(
                img_bytes, "jpg", "merchant/white_bg_clean",
                bucket_name=settings.OSS_PRIVATE_BUCKET_NAME
            )

            # 存带水印版
            watermarked = image_composer.add_ai_watermark(img_bytes)
            watermarked = image_composer.add_ai_metadata(watermarked)
            watermarked_url = await oss_service.upload_file(watermarked, "jpg", "merchant/white_bg")

            return [{"watermarked": watermarked_url, "clean": clean_url}]

        except Exception as e:
            print(f"[SUITE] 白底图生成失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    @staticmethod
    async def generate_scene_images(
        cloth_url: str,
        analysis: Dict,
        scene_count: int = 4,
    ) -> List[dict]:
        """生成场景图（图片O1直接生成）"""
        import asyncio
        import random

        selling_points = analysis.get("selling_points", [])
        product_name = analysis.get("product_name", "商品")
        product_appearance = analysis.get("product_appearance", "")

        scene_prompts = analysis.get("scene_prompts", [])
        if not scene_prompts:
            scenes = analysis.get("scenes", ["现代客厅", "户外阳光", "简约办公桌", "自然光环境"])
            scene_prompts = [
                {"selling_point": selling_points[i % len(selling_points)] if selling_points else "",
                 "scene": scenes[i % len(scenes)]}
                for i in range(max(len(scenes), scene_count))
            ]

        target_language = analysis.get("target_language", "英语")
        subtitle_suffix_map = {
            "中文": "精选推荐", "英语": "Featured", "日语": "おすすめ",
            "德语": "Empfohlen", "法语": "Recommandé", "西班牙语": "Recomendado",
            "意大利语": "Consigliato", "葡萄牙语": "Recomendado",
            "俄语": "Рекомендуем", "韩语": "추천",
        }
        subtitle_suffix = subtitle_suffix_map.get(target_language, "Featured")

        semaphore = asyncio.Semaphore(3)

        import random as _random
        from collections import defaultdict

        by_sp = defaultdict(list)
        for item in scene_prompts:
            by_sp[item.get("selling_point", "")].append(item)

        for sp in by_sp:
            _random.shuffle(by_sp[sp])

        selected_prompts = []
        sp_keys = list(by_sp.keys())
        _random.shuffle(sp_keys)
        sp_idx = {sp: 0 for sp in sp_keys}

        while len(selected_prompts) < scene_count:
            added = False
            for sp in sp_keys:
                if sp_idx[sp] < len(by_sp[sp]):
                    selected_prompts.append(by_sp[sp][sp_idx[sp]])
                    sp_idx[sp] += 1
                    added = True
                    if len(selected_prompts) >= scene_count:
                        break
            if not added:
                break

        while len(selected_prompts) < scene_count:
            selected_prompts.append(_random.choice(scene_prompts))
        selected_prompts = selected_prompts[:scene_count]

        print(f"[SUITE] 选中 {len(selected_prompts)} 个场景，"
              f"卖点：{[p.get('selling_point', '?') for p in selected_prompts]}")

        async def gen_one(i):
            async with semaphore:
                item = selected_prompts[i]
                scene = item.get("scene", "")
                selling_point = item.get("selling_point", "")
                interaction = item.get("interaction", "")
                scene_type = item.get("scene_type", "")

                o1_prompt = (
                    f"保留参考图中产品的精确外观，包括所有颜色、材质、表面质感、"
                    f"可辨识的文字、数字、图标、刻度和特殊细节。"
                    f"产品外观特征：{product_appearance}。"
                    f"将产品自然地放入以下场景中：{scene}。"
                    f"产品与场景的互动方式：{interaction}。"
                    f"场景类型：{scene_type}。"
                    f"光影自然融合，色调统一，专业产品摄影，4K高清。"
                    f"只改变背景和产品的位置/环境，不改变产品本身的任何细节。"
                )

                def _gen():
                    print(f"[SUITE-O1] 场景{i+1} prompt: {o1_prompt[:120]}...")
                    try:
                        task_id = kling_service.generate_image_o1(
                            prompt=o1_prompt,
                            image_urls=[cloth_url],
                            resolution="2k",
                            aspect_ratio="1:1",
                            n=1,
                        )
                        result = kling_service.wait_for_o1_result(task_id, max_wait=600)
                        return result.get("output_url", "")
                    except Exception as e:
                        print(f"[SUITE-O1] 场景{i+1} 失败: {e}")
                        return ""

                img_url = await asyncio.to_thread(_gen)
                return (i, img_url, selling_point)

        tasks = [gen_one(i) for i in range(scene_count)]
        raw_results = await asyncio.gather(*tasks)

        results = []
        for i, img_url, selling_point in raw_results:
            if not img_url:
                print(f"[SUITE-O1] 场景图 {i+1} 生成失败")
                continue

            try:
                resp = requests.get(img_url, timeout=60)
                img_bytes = resp.content

                title = selling_point if selling_point else product_name
                subtitle = f"{product_name} · {subtitle_suffix}"
                template_idx = i % 5

                temp_url = await oss_service.upload_file(
                    img_bytes, "jpg", "merchant/temp"
                )

                text_bytes = image_composer.add_scene_text_with_template(
                    temp_url,
                    title=title,
                    subtitle=subtitle,
                    template_idx=template_idx,
                )

                if not text_bytes:
                    text_bytes = img_bytes

                # 存无水印版
                clean_url = await oss_service.upload_file(
                    text_bytes, "jpg", "merchant/scene_with_text_clean",
                    bucket_name=settings.OSS_PRIVATE_BUCKET_NAME
                )

                # 存带水印版
                watermarked = image_composer.add_ai_watermark(text_bytes)
                watermarked = image_composer.add_ai_metadata(watermarked)
                watermarked_url = await oss_service.upload_file(
                    watermarked, "jpg", "merchant/scene_with_text"
                )

                results.append({
                    "watermarked": watermarked_url,
                    "clean": clean_url,
                })
                print(f"[SUITE-O1] ✅ 场景图 {i+1} 完成（模板{template_idx}）")

            except Exception as e:
                print(f"[SUITE-O1] 场景图 {i+1} 后处理失败: {e}")
                import traceback
                traceback.print_exc()

        return results

    @staticmethod
    async def _fallback_generate_scenes(cloth_url, analysis, scene_count):
        """图片O1不需要降级方案，直接返回空"""
        print("[SUITE-O1] 图片O1模式无需降级方案")
        return []
    
    @staticmethod
    async def generate_aplus_images(
        cloth_url: str,
        analysis: Dict,
        count: int = 2,
    ) -> List[dict]:
        """生成 A+ 图（多模板 + 多角度 + 并行 + 全局限流）"""
        import asyncio

        product_name = analysis.get("product_name", "商品")
        selling_points = analysis.get("selling_points", [])
        scenes = analysis.get("scenes", ["生活场景", "使用场景"])

        ANGLES = [
            "正面视角", "45度侧视角", "侧面视角",
            "俯视视角", "特写视角", "背面视角"
        ]

        target_language = analysis.get("target_language", "英语")
        subtitle_suffix_map = {
            "中文": "精选推荐", "英语": "Featured Recommendation",
            "日语": "おすすめ商品", "德语": "Empfohlene Auswahl",
            "法语": "Recommandation", "西班牙语": "Recomendación",
            "意大利语": "Raccomandazione", "葡萄牙语": "Recomendação",
            "俄语": "Рекомендуем", "韩语": "추천 상품",
        }
        subtitle_suffix = subtitle_suffix_map.get(target_language, "Featured")

        # ========== 全局限流：所有 A+ 图共用 ==========
        # 最多 2 个 O1 并发，避免触发可灵 1303 限制
        global_o1_sem = asyncio.Semaphore(2)

        # ========== A+ 图并发控制 ==========
        semaphore = asyncio.Semaphore(2)

        async def gen_one(i):
            async with semaphore:
                template_idx = i % 6
                angle = ANGLES[i % len(ANGLES)]
                scene = scenes[i % len(scenes)]
                selling_point = selling_points[i % len(selling_points)] if selling_points else product_name

                print(f"[SUITE-A+] A+图 {i+1}/{count}, 模板{template_idx+1}")

                title = selling_point
                subtitle = f"{product_name} - {subtitle_suffix}"
                product_appearance = analysis.get("product_appearance", "")
                product_color = analysis.get("main_color", "")

                # ========== 通用生成函数（都走全局限流） ==========
                async def _gen_async(prompt_text, log_prefix):
                    async with global_o1_sem:
                        def _sync():
                            try:
                                task_id = kling_service.generate_image_o1(
                                    prompt=prompt_text, image_urls=[cloth_url],
                                    resolution="2k", aspect_ratio="1:1", n=1,
                                )
                                result = kling_service.wait_for_o1_result(task_id, max_wait=600)
                                return result.get("output_url", "")
                            except Exception as e:
                                print(f"[SUITE-A+] {log_prefix}失败: {e}")
                                return ""
                        return await asyncio.to_thread(_sync)

                def _make_scene_prompt(scene_text, angle_text):
                    return (
                        f"保留参考图中产品的精确外观，包括所有颜色、材质、细节。"
                        f"产品外观特征：{product_appearance}。"
                        f"场景：{scene_text}。"
                        f"画面中有人物或真实环境正在使用这个产品，展示产品的实际用途和功能。"
                        f"互动方式：{angle_text}。"
                        f"光影自然融合，专业产品摄影，4K高清，无文字，无水印。"
                    )

                def _make_closeup_prompt(angle_desc, bg_desc="纯色浅灰背景"):
                    return (
                        f"保留参考图中产品的精确外观。产品外观特征：{product_appearance}。"
                        f"{angle_desc}，{bg_desc}，产品居中，无文字，无人物，无其他物品。"
                        f"专业产品摄影，4K高清。"
                    )


                def _make_usage_prompt(scene_text, index=0):
                    """生成使用场景图（必须有人物/环境正在使用产品）"""
                    scene_prompts = analysis.get("scene_prompts", [])
                    if scene_prompts and index < len(scene_prompts):
                        item = scene_prompts[index]
                        scene_desc = item.get("scene", scene_text)
                        interaction = item.get("interaction", "")
                    else:
                        scene_desc = scene_text
                        interaction = ""

                    return (
                        f"保留参考图中产品的精确外观，包括所有颜色、材质、细节。"
                        f"产品外观特征：{product_appearance}。"
                        f"**画面必须有真人正在使用这个产品**，"
                        f"人物的手或身体与产品有直接接触，"
                        f"展现产品在实际生活中的使用方式。"
                        f"场景：{scene_desc}。"
                        f"互动方式：{interaction}。"
                        f"真实生活摄影风格，光影自然，4K高清，无文字。"
                    )

                # 准备 contents
                contents = {
                    "title": title,
                    "subtitle": subtitle,
                }

                if template_idx == 0:
                    # 左文右图（使用场景图）
                    contents["main_image"] = await _gen_async(
                        _make_usage_prompt(scene, index=0), "主图O1"
                    )

                elif template_idx == 1:
                    # 上文下图（使用场景图）
                    contents["main_image"] = await _gen_async(
                        _make_usage_prompt(scene, index=0), "主图O1"
                    )

                elif template_idx == 2:
                    # 三图并列（都是使用场景）
                    results = await asyncio.gather(
                        _gen_async(_make_usage_prompt(scene, index=0), "图1"),
                        _gen_async(_make_usage_prompt(scene, index=1), "图2"),
                        _gen_async(_make_usage_prompt(scene, index=2), "图3"),
                        return_exceptions=True,
                    )
                    contents["image_1"] = results[0] if isinstance(results[0], str) else ""
                    contents["image_2"] = results[1] if isinstance(results[1], str) else ""
                    contents["image_3"] = results[2] if isinstance(results[2], str) else ""

                elif template_idx == 3:
                    # 左 3 特写 + 右大场景（并行，4 张图）
                    results = await asyncio.gather(
                        _gen_async(_make_usage_prompt(scene, index=0), "场景1"),
                        _gen_async(_make_usage_prompt(scene, index=1), "场景2"),
                        _gen_async(_make_usage_prompt(scene, index=2), "场景3"),
                        _gen_async(_make_closeup_prompt("正面视角特写"), "特写"),
                        return_exceptions=True,
                    )
                    contents["closeup_1"] = results[0] if isinstance(results[0], str) else ""
                    contents["closeup_2"] = results[1] if isinstance(results[1], str) else ""
                    contents["closeup_3"] = results[2] if isinstance(results[2], str) else ""
                    contents["scene_image"] = results[3] if isinstance(results[3], str) else ""

                elif template_idx == 4:
                    # 双场景对比（并行）
                    scene2 = scenes[(i + 1) % len(scenes)]
                    angle2 = ANGLES[(i + 2) % len(ANGLES)]
                    results = await asyncio.gather(
                        _gen_async(_make_usage_prompt(scene, index=0), "左图"),
                        _gen_async(_make_usage_prompt(scene, index=1), "右图"),
                        return_exceptions=True,
                    )
                    contents["image_left"] = results[0] if isinstance(results[0], str) else ""
                    contents["image_right"] = results[1] if isinstance(results[1], str) else ""
                    contents["label_left"] = selling_point[:20]
                    contents["label_right"] = (selling_points[(i + 1) % len(selling_points)]
                                               if len(selling_points) > 1 else title)[:20]

                elif template_idx == 5:
                    # 左侧：1 张特写 + 1 张使用场景 + 右侧产品整体介绍
                    sp1 = selling_points[0] if len(selling_points) > 0 else product_name
                    sp2 = selling_points[1] if len(selling_points) > 1 else (selling_points[0] if selling_points else product_name)

                    prompt_top = _make_closeup_prompt("正面视角特写", "纯色深灰背景")
                    prompt_bottom = _make_usage_prompt(scene, index=1)

                    results = await asyncio.gather(
                        _gen_async(prompt_top, "特写图"),
                        _gen_async(prompt_bottom, "使用场景图"),
                        return_exceptions=True,
                    )

                    contents["image_top"] = results[0] if isinstance(results[0], str) else ""
                    contents["image_bottom"] = results[1] if isinstance(results[1], str) else ""
                    contents["label_top"] = sp1
                    contents["label_bottom"] = sp2

                    # 标题截到 15 字
                    short_title = product_name if len(product_name) <= 15 else product_name[:14] + "…"
                    contents["title"] = short_title

                    if selling_points:
                        sp = selling_points[0]
                        contents["subtitle"] = sp if len(sp) <= 22 else sp[:21] + "…"
                    else:
                        contents["subtitle"] = f"{product_name} · {subtitle_suffix}"

                    # 正文：类型 + 材质 + 适用人群（跟随语言）
                    body_label_map = {
                        "中文": {"category": "类型", "material": "材质", "audience": "适用"},
                        "英语": {"category": "Type", "material": "Material", "audience": "For"},
                        "日语": {"category": "タイプ", "material": "素材", "audience": "対象"},
                        "德语": {"category": "Typ", "material": "Material", "audience": "Für"},
                        "法语": {"category": "Type", "material": "Matériau", "audience": "Pour"},
                        "西班牙语": {"category": "Tipo", "material": "Material", "audience": "Para"},
                        "意大利语": {"category": "Tipo", "material": "Materiale", "audience": "Per"},
                        "葡萄牙语": {"category": "Tipo", "material": "Material", "audience": "Para"},
                        "俄语": {"category": "Тип", "material": "Материал", "audience": "Для"},
                        "韩语": {"category": "유형", "material": "소재", "audience": "대상"},
                    }
                    body_labels = body_label_map.get(target_language, body_label_map["英语"])

                    audience = analysis.get("target_audience", "")
                    category = analysis.get("category", "")
                    material = analysis.get("material", "")

                    body_parts = []
                    if category:
                        body_parts.append(f"{body_labels['category']}: {category}")
                    if material:
                        body_parts.append(f"{body_labels['material']}: {material}")
                    if audience:
                        body_parts.append(f"{body_labels['audience']}: {audience}")

                    body_text = "  ·  ".join(body_parts)
                    if len(body_text) > 50:
                        body_text = body_text[:49] + "…"
                    contents["body"] = body_text

                image_keys = [
                    "main_image", "image_1", "image_2", "image_3",
                    "image_left", "image_right",
                    "closeup_1", "closeup_2", "closeup_3",
                    "scene_image",
                    "image_top", "image_bottom",   # 新增
                    "left_image", "right_image",
                ]
                has_image = any(contents.get(k) for k in image_keys)
                if not has_image:
                    print(f"[SUITE-A+] A+图 {i+1} 没有生成任何图片，跳过")
                    return None

                template_name = f"template_{template_idx + 1:02d}"
                aplus_bytes = aplus_renderer.render(template_name, contents, product_color)

                if aplus_bytes:
                    # 存无水印版
                    clean_url = await oss_service.upload_file(
                        aplus_bytes, "jpg", "merchant/aplus_clean",
                        bucket_name=settings.OSS_PRIVATE_BUCKET_NAME
                    )

                    # 存带水印版
                    watermarked = image_composer.add_ai_watermark(aplus_bytes)
                    watermarked = image_composer.add_ai_metadata(watermarked)
                    watermarked_url = await oss_service.upload_file(
                        watermarked, "jpg", "merchant/aplus"
                    )

                    print(f"[SUITE-A+] A+图 {i+1} 完成: {watermarked_url}")
                    return {
                        "watermarked": watermarked_url,
                        "clean": clean_url,
                    }
                else:
                    print(f"[SUITE-A+] A+图 {i+1} 渲染失败")
                    return None

        tasks = [gen_one(i) for i in range(count)]
        raw_results = await asyncio.gather(*tasks)
        results = [url for url in raw_results if url]
        # ==================================

        return results


suite_generator = SuiteGenerator()