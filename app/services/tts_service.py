"""
阿里云 DashScope TTS 服务
"""
import base64
import dashscope
from app.config import settings


class TTSService:
    def __init__(self):
        # 设置 API Key
        dashscope.api_key = settings.DASHSCOPE_API_KEY
    
    def text_to_speech(self, text: str, voice: str = "Cherry") -> bytes:
        """
        将文字转换为语音
        
        Args:
            text: 要转换的文字
            voice: 音色，可选: Cherry(女声), Stella(女声), Luna(女声), 
                   Celine(女声), 或参考官方文档
        
        Returns:
            MP3 音频二进制数据
        """
        try:
            response = dashscope.MultiModalConversation.call(
                model="qwen3-tts-flash-realtime",
                text=text,
                voice=voice
            )
            
            if response.status_code == 200:
                # 解码 Base64 音频数据
                audio_data = base64.b64decode(response.output.audio)
                return audio_data
            else:
                raise Exception(f"TTS 调用失败: {response.message}")
        except Exception as e:
            raise Exception(f"TTS 错误: {str(e)}")


# 创建全局实例
tts_service = TTSService()