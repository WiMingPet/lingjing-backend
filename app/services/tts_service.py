"""
腾讯云 TTS 服务
"""
import base64
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.tts.v20190823 import tts_client, models
from app.config import settings


# ========== 音色映射表：名字 → 腾讯云 VoiceType ==========
VOICE_MAP = {
    "温柔女声": 101001,
    "播报男声": 101002,
    "钓系女友": 101003,
    "自然男声": 101004,
    "知性女声": 101005,
    "晓晓": 101001,
    "云希": 101002,
    "晓伊": 101003,
    "云健": 101004,
    "晓悠": 101005,
}

def get_voice_type(voice_name: str) -> int:
    """根据音色名称获取腾讯云 VoiceType"""
    return VOICE_MAP.get(voice_name, 101001)


class TTSService:
    def __init__(self):
        self.cred = credential.Credential(
            settings.TENCENT_SECRET_ID,
            settings.TENCENT_SECRET_KEY
        )
        self.client = tts_client.TtsClient(self.cred, "ap-guangzhou")
    
    def text_to_speech(self, text: str, voice_type: int = 101001) -> bytes:
        if len(text) > 150:
            text = text[:150]
        
        req = models.TextToVoiceRequest()
        req.Text = text
        req.SessionId = str(hash(text))[:32]
        req.VoiceType = voice_type
        req.Codec = "mp3"
        req.Speed = 0
        req.Volume = 0
        req.PrimaryLanguage = 1
        
        resp = self.client.TextToVoice(req)
        audio_data = base64.b64decode(resp.Audio)
        print(f"[DEBUG] 腾讯云TTS成功，音色ID: {voice_type}, 音频大小: {len(audio_data)} bytes")
        return audio_data


tts_service = TTSService()