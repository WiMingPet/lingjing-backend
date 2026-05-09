"""
腾讯云 TTS 服务
"""
import base64
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.tts.v20190823 import tts_client, models
from app.config import settings


VOICE_MAP = {
    # ========== 腾讯云音色（全部实测验证） ==========
    "智小柔": 502001,
    "智小敏": 502003,
    "智小虎": 502007,
    "智小悟": 502006,
    "智小满": 502004,
    "智希": 101026,
    "暖心阿灿": 602004,
    "专业梓欣": 602005,
    "随和老李": 603003,
    "温柔小柠": 603004,
    "知心大林": 603005,
    "爱小悠": 602003,
    "爱小川": 601011,
    "爱小芊": 601009,
    "爱小娇": 601010,
    "月华": 501004,
    "浅草": 501007,
    "飞狼": 601002,
    "千键": 601003,
    "爱小家": 601005,
    
    # ========== 保留旧名称兼容 ==========
    "温柔女声": 502001,
    "播报男声": 502006,
    "钓系女友": 502003,
    "自然男声": 601011,
    "知性女声": 602003,
    "晓晓": 502001,
    "云希": 502006,
    "晓伊": 502003,
    "云健": 601011,
    "晓悠": 602003,
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
    
    def text_to_speech(self, text: str, voice_type: str = "you_pingjing") -> bytes:
        if len(text) > 300:
            text = text[:300]
        
        req = models.TextToVoiceRequest()
        req.Text = text
        req.SessionId = str(hash(text))[:32]
        req.VoiceType = voice_type  # 直接传字符串ID
        req.Codec = "mp3"
        req.Speed = 0
        req.Volume = 0
        req.PrimaryLanguage = 1
        
        resp = self.client.TextToVoice(req)
        audio_data = base64.b64decode(resp.Audio)
        print(f"[DEBUG] 腾讯云TTS成功，音色ID: {voice_type}, 音频大小: {len(audio_data)} bytes")
        return audio_data
    
    def text_to_long_speech(self, text: str, voice_type: int = 101001) -> bytes:
        """支持长文本的TTS，自动分段生成后拼接"""
        if len(text) <= 150:
            return self.text_to_speech(text, voice_type)
        
        sentences = text.replace('！', '。').replace('？', '。').split('。')
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(current_chunk) + len(sentence) < 150:
                current_chunk += sentence + "。"
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence + "。"
        if current_chunk:
            chunks.append(current_chunk)
        
        print(f"[DEBUG] TTS 长文本切分为 {len(chunks)} 段")
        
        audio_chunks = []
        for i, chunk in enumerate(chunks):
            print(f"[DEBUG] TTS 生成第 {i+1}/{len(chunks)} 段...")
            audio_data = self.text_to_speech(chunk, voice_type)
            audio_chunks.append(audio_data)
        
        return b''.join(audio_chunks)


tts_service = TTSService()