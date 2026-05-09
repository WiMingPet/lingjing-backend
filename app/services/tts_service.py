"""
腾讯云 TTS 服务
"""
import base64
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.tts.v20190823 import tts_client, models
from app.config import settings


# ========== 音色映射表：名字 → 可灵官方 Voice ID ==========
VOICE_MAP = {
    # 少年/儿童
    "阳光少年": "genshin_vindi2",
    "懂事小弟": "zhinen_xuesheng",
    "运动少年": "tiyuxi_xuedi",
    "活泼男童": "cartoon-boy-07",
    "俏皮女童": "cartoon-girl-01",
    "乖巧正太": "mengwa-v1",
    # 少女/女生
    "青春少女": "ai_shatang",
    "温柔小妹": "genshin_klee2",
    "元气少女": "genshin_kirara",
    "甜美邻家": "girlfriend_1_speech02",
    # 男性
    "阳光男生": "ai_kaiya",
    "幽默小哥": "tiexin_nanyou",
    "文艺小哥": "ai_chenjiahao_712",
    "稳重老爸": "ai_huangyaoshi_712",
    "严肃上司": "ai_laoguowang_712",
    "慈祥爷爷": "zhuxi_speech02",
    "唠叨爷爷": "uk_oldman3",
    "东北老铁": "dongbeilaotie_speech02",
    "重庆小伙": "chongqingxiaohuo_speech02",
    "潮汕大叔": "chaoshandashu_speech02",
    "台湾男生": "ai_taiwan_man2_speech02",
    "西安掌柜": "xianzhanggui_speech02",
    "新闻播报男": "diyinnansang_DB_CN_M_04-v2",
    "译制片男": "yizhipiannan-v1",
    "刀片烟嗓": "daopianyansang-v1",
    # 女性
    "温柔姐姐": "chat1_female_new-3",
    "职场女青": "girlfriend_2_speech02",
    "温柔妈妈": "you_pingjing",
    "优雅贵妇": "chengshu_jiejie",
    "唠叨奶奶": "laopopo_speech02",
    "和蔼奶奶": "heainainai_speech02",
    "四川妹子": "chuanmeizi_speech02",
    "天津姐姐": "tianjinjiejie_speech02",
    "撒娇女友": "tianmeixuemei-v1",
    # 保留兼容旧名称
    "钓系女友": "tianmeixuemei-v1",
    "温柔女声": "you_pingjing",
    "播报男声": "diyinnansang_DB_CN_M_04-v2",
    "自然男声": "ai_kaiya",
    "知性女声": "chengshu_jiejie",
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
        # 支持更长的文本（带货文案约300字）
        if len(text) > 300:
            text = text[:300]
        
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