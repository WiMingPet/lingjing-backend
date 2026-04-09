"""
阿里云 DashScope TTS 服务
"""
import base64
import dashscope
from app.config import settings


class TTSService:
    def __init__(self):
        dashscope.api_key = settings.DASHSCOPE_API_KEY
    
    def text_to_speech(self, text: str, voice: str = "Cherry") -> bytes:
        """
        将文字转换为语音，返回 MP3 音频二进制数据
        """
        # 使用 dashscope 的 audio 模块生成 MP3 格式
        from dashscope.audio.tts_v2 import SpeechSynthesizer
        
        result = SpeechSynthesizer.call(
            model="qwen3-tts-flash-realtime",
            text=text,
            voice=voice,
            format="mp3",  # 指定输出 MP3 格式
            sample_rate=24000
        )
        
        if result.get_audio_data() is not None:
            return result.get_audio_data()
        else:
            raise Exception(f"TTS 失败: {result.get_message()}")


tts_service = TTSService()