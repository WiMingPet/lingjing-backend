"""
腾讯云 TTS 服务
"""
import base64
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.tts.v20190823 import tts_client, models
from app.config import settings


class TTSService:
    def __init__(self):
        self.cred = credential.Credential(
            settings.TENCENT_SECRET_ID,
            settings.TENCENT_SECRET_KEY
        )
        self.client = tts_client.TtsClient(self.cred, "ap-guangzhou")
    
    def text_to_speech(self, text: str, voice_type: int = 1001) -> bytes:
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
        print(f"[DEBUG] 腾讯云TTS成功，音频大小: {len(audio_data)} bytes")
        return audio_data


tts_service = TTSService()