"""
视频合成服务
"""
import os
import asyncio
import subprocess
import tempfile
import requests
from typing import List


# 字体目录（兼容本地和 Docker）
FONT_DIR = "/usr/share/fonts/opentype/noto"
FONT_NAME = "Noto Sans CJK SC"


class VideoComposer:

    @staticmethod
    def _format_time(seconds: float) -> str:
        """秒 → srt 时间格式 00:00:00,000"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int(round((seconds - int(seconds)) * 1000))
        if ms == 1000:
            ms = 0
            s += 1
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    @staticmethod
    def _build_srt(scene_dialogues: list) -> str:
        """根据分镜对话，生成 srt 字幕内容（只显示对白）"""
        srt_lines = []
        idx = 1
        current_time = 0.0

        for scene in scene_dialogues:
            dialogue = scene.get("dialogue", [])
            duration = scene.get("duration", 10)

            if dialogue:
                per_line = duration / len(dialogue)
                for d in dialogue:
                    start = current_time
                    end = current_time + per_line
                    text = d.get("text", "")
                    if text.strip():
                        srt_lines.append(f"{idx}")
                        srt_lines.append(f"{VideoComposer._format_time(start)} --> {VideoComposer._format_time(end)}")
                        srt_lines.append(text)
                        srt_lines.append("")
                        idx += 1
                    current_time = end
            else:
                current_time += duration

        return "\n".join(srt_lines)

    @staticmethod
    async def compose_videos(video_urls: List[str], scene_dialogues: list = None) -> str:
        """拼接分镜（异步）+ 可选烧字幕"""
        if not video_urls:
            raise Exception("没有视频")

        video_urls = [u for u in video_urls if u]
        if not video_urls:
            raise Exception("所有分镜为空")

        def _sync_compose():
            tmp_dir = tempfile.mkdtemp()
            local_paths = []

            for i, url in enumerate(video_urls):
                path = os.path.join(tmp_dir, f"scene_{i}.mp4")
                resp = requests.get(url, timeout=120, stream=True)
                with open(path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                local_paths.append(path)

            if len(local_paths) == 1:
                merged_path = local_paths[0]
            else:
                concat_file = os.path.join(tmp_dir, "concat.txt")
                with open(concat_file, "w", encoding="utf-8") as f:
                    for path in local_paths:
                        f.write(f"file '{path}'\n")

                output_path = os.path.join(tmp_dir, "output.mp4")
                cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_file,
                    "-c", "copy",
                    output_path,
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

                if result.returncode != 0:
                    # 重新编码
                    cmd = [
                        "ffmpeg", "-y",
                        "-f", "concat",
                        "-safe", "0",
                        "-i", concat_file,
                        "-c:v", "libx264",
                        "-c:a", "aac",
                        "-preset", "fast",
                        output_path,
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
                    if result.returncode != 0:
                        raise Exception(f"FFmpeg 失败: {result.stderr[:500]}")

                merged_path = output_path

            # ★ 烧字幕（如果有对话）
            if scene_dialogues:
                srt_content = VideoComposer._build_srt(scene_dialogues)
                if srt_content.strip():
                    srt_path = os.path.join(tmp_dir, "subtitle.srt")
                    with open(srt_path, "w", encoding="utf-8") as f:
                        f.write(srt_content)

                    subtitle_output = os.path.join(tmp_dir, "output_with_subtitle.mp4")

                    # ffmpeg subtitles 滤镜路径转义
                    srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
                    font_dir_escaped = FONT_DIR.replace("\\", "/").replace(":", "\\:")

                    style = (
                        f"FontName={FONT_NAME},"
                        f"FontSize=14,"
                        f"PrimaryColour=&HFFFFFF&,"
                        f"OutlineColour=&H000000&,"
                        f"BorderStyle=1,"
                        f"Outline=2,"
                        f"Shadow=0,"
                        f"Alignment=2,"
                        f"MarginV=25"
                    )

                    cmd = [
                        "ffmpeg", "-y",
                        "-i", merged_path,
                        "-vf", f"subtitles='{srt_escaped}':fontsdir='{font_dir_escaped}':force_style='{style}'",
                        "-c:v", "libx264",
                        "-c:a", "copy",
                        "-preset", "fast",
                        subtitle_output,
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
                    if result.returncode != 0:
                        print(f"[VIDEO_COMPOSER] 烧字幕失败，返回无字幕版本: {result.stderr[:500]}")
                    else:
                        merged_path = subtitle_output
                        print(f"[VIDEO_COMPOSER] 字幕烧录成功")

            return merged_path

        return await asyncio.to_thread(_sync_compose)


video_composer = VideoComposer()