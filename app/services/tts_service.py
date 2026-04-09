"""
Edge TTS 服务 - 独立线程版本
"""
import edge_tts
import asyncio
import concurrent.futures


class TTSService:
    def __init__(self):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    
    def text_to_speech(self, text: str, voice: str = "zh-CN-XiaoxiaoNeural") -> bytes:
        """
        将文字转换为语音，返回 MP3 音频二进制数据
        """
        async def _tts():
            communicate = edge_tts.Communicate(text, voice)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            return audio_data
        
        # 在新线程中运行 asyncio.run，避免事件循环冲突
        future = self.executor.submit(asyncio.run, _tts())
        return future.result()


tts_service = TTSService()