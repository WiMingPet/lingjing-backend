"""
阿里云 DashScope TTS 服务
"""
import base64
import os
import threading
import dashscope
from dashscope.audio.qwen_tts_realtime import *
from app.config import settings


class MyCallback(QwenTtsRealtimeCallback):
    def __init__(self):
        super().__init__()
        self.audio_data = b''
        self.complete_event = threading.Event()
    
    def on_open(self) -> None:
        print('TTS connection opened')
    
    def on_close(self, close_status_code, close_msg) -> None:
        print(f'TTS connection closed: {close_status_code}, {close_msg}')
    
    def on_event(self, response: str) -> None:
        try:
            type = response['type']
            if 'response.audio.delta' == type:
                recv_audio_b64 = response['delta']
                self.audio_data += base64.b64decode(recv_audio_b64)
            if 'response.done' == type:
                self.complete_event.set()
        except Exception as e:
            print(f'TTS error: {e}')
    
    def wait_for_finished(self):
        self.complete_event.wait()


class TTSService:
    def __init__(self):
        dashscope.api_key = settings.DASHSCOPE_API_KEY
        # 国内地域使用 wss://dashscope.aliyuncs.com/api-ws/v1/realtime
        # 国际地域使用 wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime
        self.url = 'wss://dashscope.aliyuncs.com/api-ws/v1/realtime'
    
    def text_to_speech(self, text: str, voice: str = "Cherry") -> bytes:
        """将文字转换为语音，返回 MP3 音频二进制数据"""
        callback = MyCallback()
        
        qwen_tts = QwenTtsRealtime(
            model='qwen3-tts-flash-realtime',
            callback=callback,
            url=self.url
        )
        
        try:
            qwen_tts.connect()
            qwen_tts.update_session(
                voice=voice,
                response_format=AudioFormat.PCM_24000HZ_MONO_16BIT
            )
            qwen_tts.append_text(text)
            qwen_tts.finish()
            callback.wait_for_finished()
            
            return callback.audio_data
        finally:
            qwen_tts.close()


tts_service = TTSService()