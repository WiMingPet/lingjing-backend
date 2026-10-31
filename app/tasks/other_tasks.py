import asyncio
import datetime
from app.database import SessionLocal
from app.models.task import Task
from app.models.history import History
from app.utils.refund import refund_credits


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def generate_tryon_task(task_id: int, user_id: int, request_data: dict):
    return _generic_task(task_id, user_id, request_data, "tryon", "虚拟试穿")

def generate_digital_human_task(task_id: int, user_id: int, request_data: dict):
    return _generic_task(task_id, user_id, request_data, "digital_human", "数字人分身")


def generate_merchant_task(task_id: int, user_id: int, request_data: dict):
    return _generic_task(task_id, user_id, request_data, "merchant", "电商商品套图")


def generate_short_drama_task(task_id: int, user_id: int, request_data: dict):
    """AI 短剧异步任务（RQ / 本地线程共用）"""
    print(f"[SHORT_DRAMA] 开始: task_id={task_id}, user_id={user_id}")

    # 第一步：更新 processing
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return {"error": "任务不存在"}
        task.status = "processing"
        db.commit()
    finally:
        db.close()

    # 第二步：跑核心逻辑（不持有 db）
    result = None
    error = None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _generate_short_drama_core(user_id, request_data)
            )
        finally:
            loop.close()
    except (Exception, asyncio.CancelledError) as e:
        import traceback
        error = str(e) or repr(e)
        print(f"[SHORT_DRAMA] 核心失败: {error}")
        print(traceback.format_exc())

    # 第三步：更新 completed / failed + 退款 + 历史
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()

        if error:
            if task:
                task.status = "failed"
                task.error_message = error
                db.commit()
            try:
                refund_credits(db, task_id, reason=f"AI短剧失败: {error}")
            except Exception as e3:
                print(f"[SHORT_DRAMA] 退款失败: {e3}")
            return {"task_id": task_id, "status": "failed", "error": error}

        # 成功
        if task:
            task.status = "completed"
            task.output_data = result
            task.progress = 100
            task.completed_at = datetime.datetime.utcnow()
            db.commit()

        video_url = result.get("video_url")
        if video_url:
            existing = db.query(History).filter(
                History.user_id == user_id,
                History.url == video_url
            ).first()
            if not existing:
                history = History(
                    user_id=user_id,
                    url=video_url,
                    type="AI短剧",
                    thumbnail=result.get("thumbnail"),
                    created_at=datetime.datetime.utcnow()
                )
                db.add(history)
                db.commit()

        print(f"[SHORT_DRAMA] 完成: task_id={task_id}")
        return {"task_id": task_id, "status": "completed", "video_url": video_url}
    finally:
        db.close()


async def generate_short_drama_task_sync(db, user_id: int, request_data: dict) -> dict:
    """本地同步模式用（FastAPI 里 await）"""
    return await _generate_short_drama_core(user_id, request_data)


async def _generate_short_drama_core(user_id: int, request_data: dict) -> dict:
    """AI 短剧核心逻辑（异步）"""
    mode = request_data.get("mode", "real")
    theme = request_data.get("theme")
    duration = request_data.get("duration", 30)  # 单位：秒（30 或 60）
    reference_urls = request_data.get("reference_urls", [])
    language = request_data.get("language", "zh")

    # ========== 1. 校验 duration ==========
    if duration != 30:
        raise Exception(f"短剧仅支持 30 秒，当前 {duration} 秒")

    # ========== 2. 定义 style（从 mode 映射） ==========
    if mode == "anime_cn":
        style = "anime_cn"
    elif mode == "anime_jp":
        style = "anime_jp"
    elif mode == "anime_pixar":
        style = "anime_pixar"
    elif mode == "anime_us":
        style = "anime_us"
    else:
        style = "real"

    # ========== 3. 导入服务 ==========
    from app.services.script_generator import script_generator
    from app.services.character_generator import character_generator
    from app.services.scene_generator import scene_generator
    from app.services.video_composer import video_composer
    from app.services.kling import kling_service
    from app.services.oss_service import oss_service
    from app.services.video_service import VideoService

    # ========== 4. 获取剧本（用户脚本模式 或 AI 生成模式） ==========
    user_script = request_data.get("user_script")
    if user_script:
        # 用户脚本模式
        print(f"[SHORT_DRAMA] 用户脚本模式，时长 {duration} 秒")
        characters = user_script.get("characters", [])
        scenes = request_data.get("scenes", [])
        title = user_script.get("title", theme or "用户剧本")
        if not characters or not scenes:
            raise Exception("用户剧本缺少角色或分镜")
    else:
        # AI 生成模式
        reference_info = []
        if reference_urls:
            from app.services.reference_analyzer import reference_analyzer
            print(f"[SHORT_DRAMA] 分析 {len(reference_urls)} 张参考图...")
            reference_info = await reference_analyzer.analyze(reference_urls)
            print(f"[SHORT_DRAMA] 参考图分析完成: {len(reference_info)} 张")

        print(f"[SHORT_DRAMA] 生成剧本: theme={theme[:50] if theme else ''}, 参考图={len(reference_urls)}张")
        script = await script_generator.generate_script(
            theme, duration, style,
            reference_count=len(reference_urls),
            reference_info=reference_info,
            language=language,
            mode=mode,
        )
        characters = script.get("characters", [])
        scenes = script.get("scenes", [])
        title = script.get("title", (theme or "")[:20])

        if not characters or not scenes:
            raise Exception("剧本生成失败")

    print(f"[SHORT_DRAMA] 剧本: {len(characters)} 角色, {len(scenes)} 分镜, 时长 {duration} 秒")

    print(f"[SHORT_DRAMA] 生成角色定妆照...")
    character_images = await character_generator.generate_all_characters(
        characters, style, reference_urls=reference_urls
    )
    if not character_images:
        raise Exception("角色图生成失败")

    # ========== 3. 分镜生成（两轮：先生图，再生成视频） ==========
    MAX_RETRY_PER_SCENE = 2

    KLING_ACCENT_MAP = {
        "zh": "",
        "dongbei": "in Northeastern Chinese accent (东北口音)",
        "sichuan": "in Sichuan dialect (四川话)",
        "chongqing": "in Sichuan dialect with Chongqing accent (四川话/重庆口音)",
        "yue": "in Cantonese (粤语)",
        "nan": "in Hokkien / Taiwanese accent (闽南语/台湾地区口音)",
        "ja": "in Japanese",
        "en": "in English",
        "fr": "in French",
        "ko": "in Korean",
    }
    accent_hint = KLING_ACCENT_MAP.get(language, "")

    # ---------- 第一轮：生成所有分镜图 ----------
    print(f"[SHORT_DRAMA] 第一轮：生成 {len(scenes)} 张分镜图")
    scene_images = []
    for i, scene in enumerate(scenes):
        shot_prompt = scene.get("shot_prompt", "")
        characters_in_scene = scene.get("characters_in_scene", [])
        prev_img = scene_images[i - 1] if i > 0 else None

        img = await scene_generator.generate_scene_image(
            shot_prompt, character_images, characters_in_scene, style,
            prev_scene_image=prev_img,
        )
        if not img:
            raise Exception(f"段 {i+1} 生图失败")
        scene_images.append(img)
        print(f"[SHORT_DRAMA] 分镜图 {i+1}/{len(scenes)} 完成")

    # ---------- 第二轮：生成视频（不传首尾帧，智能分镜） ----------
    print(f"[SHORT_DRAMA] 第二轮：生成 {len(scenes)} 段视频")

    def _gen_video_for_scene(i: int, scene: dict, override_first_frame: str = None):
        """生成单段视频；返回 (video_url, dialogue_dict)
        - override_first_frame: 如果传了，用这个作为首帧（段间衔接用）
        """
        shot_prompt = scene.get("shot_prompt", "")
        dialogue = scene.get("dialogue", [])

        # 如果传了 override_first_frame（上一段最后一帧），用它；否则用剧本生成的分镜图
        first_frame = override_first_frame if override_first_frame else scene_images[i]
        print(f"[SHORT_DRAMA] 段 {i+1} 首帧: {'上一段最后一帧' if override_first_frame else '剧本分镜图'}")

        # 流水账里已经有对白，不要再重复"对话"部分
        # 把 dialogue 的 tone 合并到 shot_prompt 里（如果还没加）
        merged_prompt = shot_prompt
        for d in dialogue:
            char = d.get("character", "")
            tone = d.get("tone", "")
            text = d.get("text", "")
            if char and tone and text:
                for quote in ['“', '"', '「']:
                    old = f'{char}：{quote}{text}'
                    new = f'{char}（{tone}）：{quote}{text}'
                    if old in merged_prompt:
                        merged_prompt = merged_prompt.replace(old, new)
                        break

        full_prompt = merged_prompt
        if accent_hint:
            full_prompt += f"\n（{accent_hint}）"

        def _sync():
            kling_task_id = kling_service.generate_video(
                image_url=first_frame,
                prompt=full_prompt,
                duration=30,
                mode="std",
                model="4.0",
                sound="native",
                multi_shot=True,
            )
            result = kling_service.wait_for_video_result(kling_task_id, max_wait=2400)
            video_url = ""
            if result and isinstance(result, dict):
                video_url = (
                    result.get("video_url", "")
                    or result.get("task_result", {}).get("video_url", "")
                )
            return video_url

        last_err = None
        for attempt in range(1, MAX_RETRY_PER_SCENE + 1):
            try:
                print(f"[SHORT_DRAMA] 段 {i+1}/{len(scenes)} 第 {attempt} 次尝试")
                scene_video = _sync()
                if scene_video:
                    print(f"[SHORT_DRAMA] 段 {i+1} 成功")
                    return (scene_video, {"dialogue": dialogue, "duration": 30.0})
                last_err = "返回空 url"
            except Exception as e:
                last_err = str(e)
                print(f"[SHORT_DRAMA] 段 {i+1} 第 {attempt} 次失败: {e}")

                UNRETRYABLE_KEYWORDS = [
                    "Account balance not enough", "1102", "余额不足",
                    "insufficient balance", "unauthorized", "invalid api key",
                ]
                if any(kw.lower() in last_err.lower() for kw in UNRETRYABLE_KEYWORDS):
                    raise Exception(f"段 {i+1} 不可重试错误: {last_err}")

            if attempt < MAX_RETRY_PER_SCENE:
                import time
                time.sleep(5 * attempt)

        raise Exception(f"段 {i+1} 重试{MAX_RETRY_PER_SCENE}次后仍失败: {last_err}")

    video_urls = [None] * len(scenes)
    scene_dialogues = [None] * len(scenes)
    prev_last_frame_url = None  # 上一段最后一帧，作为下一段首帧

    for i in range(len(scenes)):
        print(f"[SHORT_DRAMA] 开始串行生成段 {i+1}/{len(scenes)}")

        video_url, dialogue_dict = await asyncio.to_thread(
            _gen_video_for_scene, i, scenes[i], prev_last_frame_url
        )
        video_urls[i] = video_url
        scene_dialogues[i] = dialogue_dict
        print(f"[SHORT_DRAMA] 段 {i+1} 完成: {video_url}")

        # 抽最后一帧，给下一段用（最后一段不用抽）
        if i < len(scenes) - 1:
            try:
                prev_last_frame_url = await VideoService.extract_last_frame(video_url)
                print(f"[SHORT_DRAMA] 段 {i+1} 最后一帧: {prev_last_frame_url}")
            except Exception as e:
                print(f"[SHORT_DRAMA] 抽帧失败（不影响主流程）: {e}")
                prev_last_frame_url = None

    print(f"[SHORT_DRAMA] 所有 {len(scenes)} 段生成完成")

    if any(v is None for v in video_urls):
        raise Exception("有视频生成失败")
    # ========== 分镜生成结束 ==========

    # 4. 合成（带字幕）
    print(f"[SHORT_DRAMA] 合成 {len(video_urls)} 个分镜")
    output_path = await video_composer.compose_videos(video_urls, scene_dialogues)

    # 5. 上传 OSS
    with open(output_path, "rb") as f:
        video_bytes = f.read()

    final_url = await oss_service.upload_file(video_bytes, "mp4", "short_drama")

    thumbnail = None
    try:
        thumbnail = await VideoService.extract_thumbnail(final_url)
    except Exception as e:
        print(f"[SHORT_DRAMA] 封面失败: {e}")

    print(f"[SHORT_DRAMA] 完成: {final_url}")

    return {
        "video_url": final_url,
        "thumbnail": thumbnail,
        "mode": mode,
        "theme": theme,
        "title": title,
        "character_count": len(character_images),
        "scene_count": len(video_urls),
    }


def _generic_task(task_id, user_id, request_data, task_type, task_name):
    print(f"[RQ-OTHER] 开始 {task_name}: task_id={task_id}, user_id={user_id}")

    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return {"error": "任务不存在"}

        task.status = "processing"
        db.commit()

        # ========== tryon（修复） ==========
        if task_type == "tryon":
            from app.services.tryon_service import TryonService
            result_task = _run_async(TryonService.generate_tryon(db, user_id, request_data))

            outer_task = db.query(Task).filter(Task.id == task_id).first()
            if outer_task and result_task:
                outer_task.status = result_task.status
                outer_task.output_data = result_task.output_data
                outer_task.progress = 100
                outer_task.completed_at = datetime.datetime.utcnow()
                db.commit()
                print(f"[RQ-OTHER] tryon 外层任务已同步: task_id={task_id}, status={result_task.status}")

                if result_task.status == "failed":
                    refund_credits(
                        db, task_id,
                        reason=f"虚拟试穿失败: {result_task.error_message or '未知错误'}"
                    )

        # ========== digital_human（修复） ==========
        elif task_type == "digital_human":
            from app.services.kling import kling_service
            api_task_id = _run_async(
                kling_service.generate_digital_human(
                    image_url=request_data.get("image_url"),
                    text=request_data.get("text"),
                    voice=request_data.get("voice"),
                    prompt=request_data.get("prompt"),
                )
            )
            result = kling_service.wait_for_digital_human_result(api_task_id)
            video_url = result.get("task_result", {}).get("video_url", "")

            if not video_url:
                raise Exception("数字人视频生成失败")

            thumbnail_url = None
            try:
                from app.services.video_service import VideoService
                thumbnail_url = _run_async(VideoService.extract_thumbnail(video_url))
                print(f"[RQ-OTHER] 数字人封面生成成功: {thumbnail_url}")
            except Exception as e:
                print(f"[RQ-OTHER] 数字人封面生成失败: {e}")

            task.status = "completed"
            task.output_data = {"video_url": video_url, "thumbnail": thumbnail_url}
            task.progress = 100
            task.completed_at = datetime.datetime.utcnow()
            db.commit()

            existing = db.query(History).filter(
                History.user_id == user_id, History.url == video_url
            ).first()
            if not existing:
                history = History(
                    user_id=user_id,
                    url=video_url,
                    type="数字人分身",
                    thumbnail=thumbnail_url,
                    created_at=datetime.datetime.utcnow()
                )
                db.add(history)
                db.commit()

        elif task_type == "merchant":
            from app.routers.merchant import _generate_package_logic
            import json

            cloth_urls = request_data.get("cloth_urls", [])
            template = request_data.get("template")
            product_type = request_data.get("product_type", "other")
            height = request_data.get("height")
            weight = request_data.get("weight")
            scene_count = request_data.get("scene_count", 1)
            gender = request_data.get("gender", "female")
            scene_text = request_data.get("scene_text", "")

            results = _run_async(_generate_package_logic(
                cloth_urls=cloth_urls,
                template=template,
                product_type=product_type,
                height=height,
                weight=weight,
                scene_count=scene_count,
                gender=gender,
                scene_text=scene_text,
            ))

            task.status = "completed"
            task.output_data = {"results": results}
            db.commit()

            for item in results:
                all_images = []
                all_images.extend(item.get("tryon_images", []))
                all_images.extend(item.get("main_images", []))
                all_images.extend(item.get("scene_images", []))

                if all_images:
                    existing = db.query(History).filter(
                        History.user_id == user_id,
                        History.url == json.dumps(all_images)
                    ).first()

                    if not existing:
                        history = History(
                            user_id=user_id,
                            url=json.dumps(all_images),
                            type="电商商品套图",
                            thumbnail=all_images[0],
                            created_at=datetime.datetime.utcnow()
                        )
                        db.add(history)

            db.commit()
            print(f"[RQ-OTHER] 电商套图完成: task_id={task_id}")
            return {"task_id": task_id, "status": "completed"}

    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"[RQ-OTHER] {task_name} 失败: task_id={task_id}, error={error_msg}")
        print(traceback.format_exc())

        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = "failed"
                task.error_message = error_msg
                db.commit()
        except Exception as e2:
            print(f"[RQ-OTHER] 更新失败状态出错: {e2}")

        refund_credits(db, task_id, reason=f"{task_name}失败: {error_msg}")
        return {"task_id": task_id, "status": "failed", "error": error_msg}

    finally:
        db.close()

def _merge_angle_videos_sync(video_urls: list) -> str:
    """同步版视频合并（RQ Worker 中用）"""
    import subprocess
    import tempfile
    import os
    import requests
    from app.services.oss_service import oss_service
    import asyncio

    files_to_clean = []

    try:
        video_files = []
        for url in video_urls:
            tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            resp = requests.get(url, timeout=60)
            tmp.write(resp.content)
            tmp.close()
            video_files.append(tmp.name)
            files_to_clean.append(tmp.name)

        list_file = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w")
        for vf in video_files:
            list_file.write(f"file '{vf}'\n")
        list_file.close()
        files_to_clean.append(list_file.name)

        output_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        output_file.close()
        files_to_clean.append(output_file.name)

        cmd = [
            "ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file.name,
            "-c", "copy", output_file.name, "-y"
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        with open(output_file.name, "rb") as f:
            video_bytes = f.read()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                oss_service.upload_file(video_bytes, "mp4", "multi_angle_videos")
            )
        finally:
            loop.close()

    finally:
        for f in files_to_clean:
            try:
                os.unlink(f)
            except:
                pass