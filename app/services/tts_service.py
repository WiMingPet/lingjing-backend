"""
阿里云 DashScope TTS 服务
"""
import base64
import io
import dashscope
from pydub import AudioSegment
from app.config import settings


class TTSService:
    def __init__(self):
        dashscope.api_key = settings.DASHSCOPE_API_KEY
    
    def text_to_speech(self, text: str, voice: str = "Cherry") -> bytes:
        """
        将文字转换为语音，返回 MP3 音频二进制数据
        """
        response = dashscope.MultiModalConversation.call(
            model="qwen3-tts-flash-realtime",
            text=text,
            voice=voice
        )
        
        if response.status_code == 200:
            # 获取 PCM 音频数据
            audio_b64 = response.output.audio
            pcm_data = base64.b64decode(audio_b64)
            
            # 将 PCM 转换为 MP3
            audio = AudioSegment.from_raw(
                io.BytesIO(pcm_data),
                sample_width=2,      # 16-bit
                frame_rate=24000,    # 24kHz
                channels=1           # 单声道
            )
            
            # 导出为 MP3
            mp3_buffer = io.BytesIO()
            audio.export(mp3_buffer, format="mp3", bitrate="128k")
            mp3_data = mp3_buffer.getvalue()
            
            print(f"[DEBUG] TTS 成功，MP3 大小: {len(mp3_data)} bytes")
            return mp3_data
        else:
            raise Exception(f"TTS 失败: {response.message}")


tts_service = TTSService()