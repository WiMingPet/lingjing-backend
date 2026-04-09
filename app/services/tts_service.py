"""
Edge TTS 服务 - 免费，无需 API Key
"""
import edge_tts
import asyncio


class TTSService:
    def __init__(self):
        pass
    
    def text_to_speech(self, text: str, voice: str = "zh-CN-XiaoxiaoNeural") -> bytes:
        """
        将文字转换为语音，返回 MP3 音频二进制数据
        """
        # 创建异步任务
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def _tts():
            communicate = edge_tts.Communicate(text, voice)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            return audio_data
        
        try:
            audio_data = loop.run_until_complete(_tts())
            print(f"[DEBUG] Edge TTS 成功，音频大小: {len(audio_data)} bytes")
            return audio_data
        finally:
            loop.close()


tts_service = TTSService()