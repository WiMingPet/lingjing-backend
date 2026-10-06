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
    except (Exception, asyncio.CancelledError) as e:      # ★ 加 CancelledError
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
    duration = request_data.get("duration", 1)
    reference_urls = request_data.get("reference_urls", [])
    language = request_data.get("language", "zh")

    # ★ 画风由 mode 决定，不由用户传
    if mode == "anime":
        style = "anime"          # 动漫短剧：国产 3D 动画风
    else:
        style = "realistic"      # 真人短剧：真人写实

    from app.services.script_generator import script_generator
    from app.services.character_generator import character_generator
    from app.services.scene_generator import scene_generator
    from app.services.video_composer import video_composer
    from app.services.kling import kling_service
    from app.services.oss_service import oss_service
    from app.services.video_service import VideoService

    # ★ 分析参考图（如果有）
    reference_info = []
    if reference_urls:
        from app.services.reference_analyzer import reference_analyzer
        print(f"[SHORT_DRAMA] 分析 {len(reference_urls)} 张参考图...")
        reference_info = await reference_analyzer.analyze(reference_urls)
        print(f"[SHORT_DRAMA] 参考图分析完成: {len(reference_info)} 张")

    # 1. 生成剧本（传"参考图数量"）
    print(f"[SHORT_DRAMA] 生成剧本: theme={theme[:50]}, 参考图={len(reference_urls)}张")
    script = await script_generator.generate_script(
        theme, duration, style, reference_count=len(reference_urls),
        reference_info=reference_info, 
        language=language,
        mode=mode,  
    )

    characters = script.get("characters", [])
    scenes = script.get("scenes", [])
    title = script.get("title", theme[:20])

    if not characters or not scenes:
        raise Exception("剧本生成失败")

    print(f"[SHORT_DRAMA] 剧本: {len(characters)} 角色, {len(scenes)} 分镜")

    # 2. 生成角色图（传"参考图列表"）
    print(f"[SHORT_DRAMA] 生成角色定妆照...")
    character_images = await character_generator.generate_all_characters(
        characters, style, reference_urls=reference_urls
    )
    if not character_images:
        raise Exception("角色图生成失败")

    # ========== 3. 分镜并发生成（并发4 + 重试 + 失败即中止退款） ==========
    MAX_CONCURRENT_SCENES = 3        # 并发数
    MAX_RETRY_PER_SCENE = 2          # 每个分镜最多重试2次（共3次尝试）
    sem = asyncio.Semaphore(MAX_CONCURRENT_SCENES)

    # 可灵 3.0 口音标注
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

    # 用于“一个失败就取消其他”的事件
    fail_event = asyncio.Event()
    fail_detail = {"index": None, "error": None}

    async def _gen_one_scene(i: int, scene: dict):
        """生成单个分镜；返回 (video_url, dialogue_dict)"""
        async with sem:
            if fail_event.is_set():
                raise asyncio.CancelledError(f"分镜 {i+1} 因其他分镜失败被取消")

            scene_prompt = scene.get("scene_prompt", "")
            characters_in_scene = scene.get("characters_in_scene", [])
            dialogue = scene.get("dialogue", [])

            # 先生成分镜图
            try:
                scene_img = await scene_generator.generate_scene_image(
                    scene_prompt, character_images, characters_in_scene, style
                )
            except Exception as e:
                scene_img = None
                print(f"[SHORT_DRAMA] 分镜 {i+1} 生图异常: {e}")

            if not scene_img:
                # 生图失败也算分镜失败，进入统一失败处理
                err = f"分镜 {i+1} 生图失败"
                if not fail_event.is_set():
                    fail_event.set()
                    fail_detail["index"] = i + 1
                    fail_detail["error"] = err
                raise Exception(err)

            dialogue_text = " | ".join([
                f"{d.get('character', '')}: {d.get('text', '')}"
                for d in dialogue
                if d.get("character") and d.get("text")
            ])

            # ★ 取上一个分镜的 end_action
            prev_end_action = ""
            if i > 0:
                prev_end_action = scenes[i - 1].get("end_action", "")
                if prev_end_action:
                    prev_end_action = f" Continuing from the previous scene where {prev_end_action}."

            video_prompt = (
                f"{scene_prompt}.{prev_end_action} "
                f"**Show the full action sequence smoothly, not a static pose.** "
                f"Characters are talking. "
                f"Speak the following dialogue {accent_hint}: {dialogue_text}. "
                f"Cinematic motion, natural acting, lips moving as they speak, "
                f"no text overlay."
            )

            def _gen_video():
                task_id = kling_service.generate_video(
                    image_url=scene_img,
                    prompt=video_prompt,
                    duration=10,
                    mode="std",
                    model="3.0",
                    sound="native",
                )
                result = kling_service.wait_for_video_result(task_id, max_wait=2400)
                video_url = ""
                if result and isinstance(result, dict):
                    video_url = (
                        result.get("video_url", "")
                        or result.get("task_result", {}).get("video_url", "")
                    )
                return video_url 

            last_err = None
            for attempt in range(1, MAX_RETRY_PER_SCENE + 1):
                # 每次尝试前再确认一次：别人已失败就撤
                if fail_event.is_set():
                    raise asyncio.CancelledError(f"分镜 {i+1} 因其他分镜失败被取消")

                try:
                    print(f"[SHORT_DRAMA] 分镜 {i+1}/{len(scenes)} 第 {attempt} 次尝试")
                    scene_video = await asyncio.to_thread(_gen_video)
                    if scene_video:
                        print(f"[SHORT_DRAMA] 分镜 {i+1} 成功")
                        return (scene_video, {"dialogue": dialogue, "duration": 10})
                    last_err = "返回空 url"
                    print(f"[SHORT_DRAMA] 分镜 {i+1} 返回空 url")
                except Exception as e:
                    last_err = str(e)
                    print(f"[SHORT_DRAMA] 分镜 {i+1} 第 {attempt} 次失败: {e}")

                    # ★ 不可重试错误：余额不足、鉴权失败等，直接中止
                    UNRETRYABLE_KEYWORDS = [
                        "Account balance not enough",
                        "1102",
                        "余额不足",
                        "insufficient balance",
                        "unauthorized",
                        "invalid api key",
                    ]
                    if any(kw.lower() in last_err.lower() for kw in UNRETRYABLE_KEYWORDS):
                        err = f"分镜 {i+1} 不可重试错误: {last_err}"
                        print(f"[SHORT_DRAMA] {err}")
                        if not fail_event.is_set():
                            fail_event.set()
                            fail_detail["index"] = i + 1
                            fail_detail["error"] = last_err
                        raise Exception(err)

                if attempt < MAX_RETRY_PER_SCENE:
                    await asyncio.sleep(5 * attempt)

            # 重试耗尽 → 触发全局失败
            err = f"分镜 {i+1} 重试{MAX_RETRY_PER_SCENE}次后仍失败: {last_err}"
            print(f"[SHORT_DRAMA] {err}")
            if not fail_event.is_set():
                fail_event.set()
                fail_detail["index"] = i + 1
                fail_detail["error"] = err
            raise Exception(err)

    # 启动所有分镜
    print(f"[SHORT_DRAMA] 开始并发生成 {len(scenes)} 个分镜（并发数={MAX_CONCURRENT_SCENES}）")
    tasks = [asyncio.create_task(_gen_one_scene(i, scene)) for i, scene in enumerate(scenes)]

    # gather：任一任务抛异常就立刻返回（return_exceptions=False 让异常直接冒出来）
    # 但我们要“一个失败取消其他”，所以用 wait + FIRST_EXCEPTION
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
    except Exception as e:
        # 理论到不了这
        for t in tasks:
            t.cancel()
        raise Exception(f"分镜调度异常: {e}")

    # 有任务失败 → 取消所有未完成的 → 抛异常（触发退款）
    if any(t.exception() is not None for t in done):
        for t in pending:
            t.cancel()
        # 等取消生效
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        # 收集第一个真正的错误
        err_msgs = []
        for t in done:
            exc = t.exception()
            if exc is not None:
                err_msgs.append(str(exc))
        raise Exception(
            f"分镜生成失败（分镜 {fail_detail['index']}）：{fail_detail['error']}"
            if fail_detail["index"] else
            f"分镜生成失败：{'; '.join(err_msgs) or '未知错误'}"
        )

    # 全部成功 → 按顺序取结果
    video_urls = []
    scene_dialogues = []
    for t in tasks:
        r = t.result()
        if not r or not r[0]:
            raise Exception("分镜返回空 url（异常：不应到达此分支）")
        video_urls.append(r[0])
        scene_dialogues.append(r[1])

    if not video_urls:
        raise Exception("所有分镜失败")
    # ========== 分镜并发结束 ==========

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
        
        # 根据任务类型调用对应服务
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
                
                # ========== 如果内层失败，退款 ==========
                if result_task.status == "failed":
                    refund_credits(
                        db, task_id,
                        reason=f"虚拟试穿失败: {result_task.error_message or '未知错误'}"
                    )
                # ============================================
        
        
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
            
            # 生成封面
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
                    thumbnail=thumbnail_url,  # ← 加封面
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
            
            # 调用核心生成逻辑
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
            
            # 更新任务
            task.status = "completed"
            task.output_data = {"results": results}
            db.commit()
            
            # 保存历史记录
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
        # 下载所有视频（同步版）
        video_files = []
        for url in video_urls:
            tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            resp = requests.get(url, timeout=60)
            tmp.write(resp.content)
            tmp.close()
            video_files.append(tmp.name)
            files_to_clean.append(tmp.name)
        
        # 创建 concat 文件列表
        list_file = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w")
        for vf in video_files:
            list_file.write(f"file '{vf}'\n")
        list_file.close()
        files_to_clean.append(list_file.name)
        
        # ffmpeg 合并
        output_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        output_file.close()
        files_to_clean.append(output_file.name)
        
        cmd = [
            "ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file.name,
            "-c", "copy", output_file.name, "-y"
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # 上传到 OSS
        with open(output_file.name, "rb") as f:
            video_bytes = f.read()
        
        # 同步上传（用 asyncio 执行异步方法）
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