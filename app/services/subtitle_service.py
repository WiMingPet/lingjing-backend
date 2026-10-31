import whisper
import os
import tempfile
import requests
from typing import List, Dict

class SubtitleService:
    def __init__(self):
        # 加载 base 模型（服务器内存不够用 tiny，追求准用 small）
        self.model = whisper.load_model("base")

    def generate_subtitles(self, video_url: str) -> List[Dict]:
        """
        下载视频，提取音频，用 whisper 识别，返回带时间戳的文本列表
        """
        # 1. 下载视频
        tmp_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        try:
            resp = requests.get(video_url, timeout=120)
            with open(tmp_video.name, "wb") as f:
                f.write(resp.content)

            # 2. whisper 识别（会自动提取音频）
            result = self.model.transcribe(tmp_video.name, language="zh")
            
            # 3. 转换为 video_composer 需要的格式
            subtitles = []
            for seg in result.get("segments", []):
                text = seg.get("text", "").strip()
                if text:
                    subtitles.append({
                        "start": seg["start"],
                        "end": seg["end"],
                        "text": text
                    })
            
            return subtitles
        finally:
            if os.path.exists(tmp_video.name):
                os.unlink(tmp_video.name)

subtitle_service = SubtitleService()