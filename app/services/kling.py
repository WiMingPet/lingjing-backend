"""
可灵AI API 调用服务 - 基于官方文档一次性修复
"""
import requests
import jwt
import time
from typing import Dict, Optional, List
from app.config import settings
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type


class KlingService:
    """可灵AI API 服务"""
    
    def __init__(self):
        self.api_url = settings.KLING_API_URL
        self.access_key = settings.KLING_API_KEY
        self.secret_key = settings.KLING_API_SECRET
    
    def _generate_token(self) -> str:
        """生成JWT Token"""
        headers = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "iss": self.access_key,
            "exp": int(time.time()) + 1800,
            "nbf": int(time.time()) - 5
        }
        token = jwt.encode(payload, self.secret_key, algorithm="HS256", headers=headers)
        return token
    
    def _get_headers(self) -> Dict:
        """获取请求头"""
        token = self._generate_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def _get_base_url(self) -> str:
        """获取完整的 API 基础 URL，确保包含 /v1"""
        base_url = self.api_url.rstrip('/')
        if not base_url.endswith('/v1'):
            base_url = f"{base_url}/v1"
        return base_url
    
    # ========== 图片生成（文生图 + 图生图）==========
    def generate_image(self, prompt: str, negative_prompt: str = "", 
                       width: int = 512, height: int = 512, 
                       num_images: int = 1,
                       reference_image_url: str = None) -> str:
        """
        生成图片
        - 有 reference_image_url: 图生图（通过 image 参数）
        - 无 reference_image_url: 文生图
        返回 task_id
        """
        base_url = self._get_base_url()
        url = f"{base_url}/images/generations"
        
        # 计算宽高比
        if width > height:
            aspect_ratio = "16:9"
        elif height > width:
            aspect_ratio = "9:16"
        else:
            aspect_ratio = "1:1"
        
        # 构建请求参数
        payload = {
            "model_name": "kling-v2-1",
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "aspect_ratio": aspect_ratio,
            "n": num_images
        }
        
        # 如果有参考图，添加 image 参数实现图生图
        if reference_image_url:
            payload["image"] = reference_image_url
            print(f"[DEBUG] 使用图生图模式，参考图: {reference_image_url}")
        else:
            print(f"[DEBUG] 使用文生图模式")
        
        print(f"[DEBUG] 请求URL: {url}")
        print(f"[DEBUG] 请求参数: {payload}")
        response = requests.post(url, json=payload, headers=self._get_headers())
        result = response.json()
        print(f"[DEBUG] 响应状态码: {response.status_code}")
        print(f"[DEBUG] 响应内容: {response.text}")
        
        if result.get("code") != 0:
            raise Exception(f"可灵API错误: {result.get('message')}")
        
        return result["data"]["task_id"]
    
    def get_task_status(self, task_id: str) -> Dict:
        """查询图片任务状态"""
        base_url = self._get_base_url()
        url = f"{base_url}/images/generations/{task_id}"
        response = requests.get(url, headers=self._get_headers())
        result = response.json()
        
        if result.get("code") != 0:
            raise Exception(f"查询失败: {result.get('message')}")
        
        return result["data"]
    
    def wait_for_result(self, task_id: str, task_type: str = "image", 
                        max_wait: int = 120, poll_interval: int = 2) -> Dict:
        """轮询等待图片任务完成"""
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            status_data = self.get_task_status(task_id)
            task_status = status_data.get("task_status")
            
            if task_status == "succeed":
                return status_data
            elif task_status == "failed":
                error_msg = status_data.get("task_status_msg", "未知错误")
                raise Exception(f"任务失败: {error_msg}")
            
            time.sleep(poll_interval)
        
        raise Exception(f"任务超时，task_id: {task_id}")
    
    # ========== 视频生成（图生视频 + 文生视频）==========
    def generate_video(self, image_url: str = None, prompt: str = "", 
                       duration: int = 5, mode: str = "std") -> str:
        """
        生成视频
        - 有 image_url: 图生视频
        - 无 image_url: 文生视频
        返回 task_id
        """
        base_url = self._get_base_url()
        url = f"{base_url}/videos/image2video"
        
        payload = {
            "model_name": "kling-v2-6",
            "prompt": prompt,
            "duration": str(duration),
            "mode": mode,
            "with_audio": True  # ← 添加这一行，开启音频
        }
        
        # 如果有图片，添加 image 参数实现图生视频
        if image_url:
            payload["image"] = image_url
            print(f"[DEBUG] 使用图生视频模式，参考图: {image_url}")
        else:
            print(f"[DEBUG] 使用文生视频模式")
        
        print(f"[DEBUG] 视频生成请求URL: {url}")
        print(f"[DEBUG] 视频生成请求参数: {payload}")
        response = requests.post(url, json=payload, headers=self._get_headers())
        result = response.json()
        print(f"[DEBUG] 视频生成响应: {result}")
        
        if result.get("code") != 0:
            raise Exception(f"可灵视频API错误: {result.get('message')}")
        
        return result["data"]["task_id"]
    
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(Exception))
    def get_video_task_status(self, task_id: str) -> Dict:
        """查询视频任务状态（带重试）"""
        base_url = self._get_base_url()
        url = f"{base_url}/videos/image2video/{task_id}"
        response = requests.get(url, headers=self._get_headers(), timeout=30)
        result = response.json()
        
        if result.get("code") != 0:
            raise Exception(f"查询视频任务失败: {result.get('message')}")
        
        return result["data"]
    
    def wait_for_video_result(self, task_id: str, max_wait: int = 600, 
                              poll_interval: int = 15) -> Dict:
        """轮询等待视频任务完成（优化版：降低频率，避免并发限制）"""
        import time as time_module
        start_time = time_module.time()
        
        # 初始轮询间隔15秒，逐步递增到30秒
        current_interval = poll_interval
        
        while time_module.time() - start_time < max_wait:
            try:
                status_data = self.get_video_task_status(task_id)
                task_status = status_data.get("task_status")
                print(f"[DEBUG] 视频任务状态: {task_status}")
                
                if task_status == "succeed":
                    task_result = status_data.get("task_result", {})
                    videos = task_result.get("videos", [])
                    if videos:
                        status_data["task_result"]["video_url"] = videos[0].get("url", "")
                    return status_data
                elif task_status == "failed":
                    error_msg = status_data.get("task_status_msg", "未知错误")
                    raise Exception(f"视频任务失败: {error_msg}")
            except Exception as e:
                # 如果是并发限制错误，退避重试
                if "parallel task" in str(e).lower() or "1303" in str(e):
                    print(f"[DEBUG] 并发限制，稍后重试...")
                    time_module.sleep(current_interval * 2)
                    continue
                raise e
            
            time_module.sleep(current_interval)
            # 逐步递增间隔，最大30秒
            current_interval = min(current_interval + 5, 30)
        
        raise Exception(f"视频任务超时，task_id: {task_id}")
    
    # ========== 虚拟试穿（独立API）==========
    def generate_tryon(self, human_image_url: str, cloth_image_url: str, cloth_category: str = None, digital_human_id: str = None) -> str:
        """
        虚拟试穿 - 使用独立API
        参数名严格按照官方文档: human_image, cloth_image
        返回 task_id
        """
        base_url = self._get_base_url()
        url = f"{base_url}/images/kolors-virtual-try-on"
        
        payload = {
            "model_name": "kolors-virtual-try-on-v1-5",
            "human_image": human_image_url,
            "cloth_image": cloth_image_url
        }
        if cloth_category:
            payload["cloth_category"] = cloth_category
        # 如果有数字人ID，添加到请求中（如果API支持）
        if digital_human_id:
            payload["digital_human_id"] = digital_human_id
        
        print(f"[DEBUG] 虚拟试穿请求URL: {url}")
        print(f"[DEBUG] 虚拟试穿请求参数: {payload}")
        response = requests.post(url, json=payload, headers=self._get_headers())
        result = response.json()
        print(f"[DEBUG] 虚拟试穿响应: {result}")
        
        if result.get("code") != 0:
            raise Exception(f"可灵虚拟试穿API错误: {result.get('message')}")
        
        return result["data"]["task_id"]
    
    def get_tryon_task_status(self, task_id: str) -> Dict:
        """查询虚拟试穿任务状态"""
        base_url = self._get_base_url()
        url = f"{base_url}/images/kolors-virtual-try-on/{task_id}"
        response = requests.get(url, headers=self._get_headers())
        result = response.json()
        
        if result.get("code") != 0:
            raise Exception(f"查询虚拟试穿任务失败: {result.get('message')}")
        
        return result["data"]
    
    def wait_for_tryon_result(self, task_id: str, max_wait: int = 300, 
                              poll_interval: int = 15) -> Dict:
        """轮询等待虚拟试穿任务完成"""
        start_time = time.time()
        current_interval = poll_interval
        
        while time.time() - start_time < max_wait:
            try:
                status_data = self.get_tryon_task_status(task_id)
                task_status = status_data.get("task_status")
                print(f"[DEBUG] 虚拟试穿任务状态: {task_status}")
                
                if task_status == "succeed":
                    return status_data
                elif task_status == "failed":
                    error_msg = status_data.get("task_status_msg", "未知错误")
                    raise Exception(f"虚拟试穿任务失败: {error_msg}")
            except Exception as e:
                if "parallel task" in str(e).lower() or "1303" in str(e):
                    print(f"[DEBUG] 并发限制，稍后重试...")
                    time.sleep(current_interval * 2)
                    continue
                raise e
            
            time.sleep(current_interval)
            current_interval = min(current_interval + 5, 30)
        
        raise Exception(f"虚拟试穿任务超时，task_id: {task_id}")
    
    # ========== 数字人分身 ==========
    async def generate_digital_human(self, digital_human_id: Optional[int] = None, text: str = "", image_url: str = None, audio_url: str = None, prompt: str = None, name: str = None, voice: str = None) -> str:
        """
        数字人分身 - 照片+文字/音频生成视频
        支持两种模式：
        1. 提供 text：自动用 TTS 生成音频
        2. 提供 audio_url：直接使用音频文件
        """
        import os
        import uuid
        import time
        from app.services.tts_service import tts_service
        from app.services.oss_service import oss_service

        base_url = self._get_base_url()
        url = f"{base_url}/videos/avatar/image2video"

        # 使用可灵官方音色生成TTS音频
        if not audio_url and text:
            from app.services.tts_service import tts_service, get_voice_type
            voice_type = get_voice_type(voice) if voice else 502001
            audio_data = tts_service.text_to_long_speech(text, voice_type)
            audio_url = await oss_service.upload_file(audio_data, "mp3", "digital_human/audio")
            print(f"[DEBUG] TTS 生成音频成功, 音色ID: {voice_type}, 文本: {text[:50]}...")

        if not audio_url:
            raise Exception("请提供文字内容或音频文件")

        # ========== 强制生成唯一的 external_task_id ==========
        # 忽略前端传入的 name，使用 UUID + 时间戳生成唯一 ID
        unique_task_id = f"dh_{uuid.uuid4().hex}_{int(time.time())}"
        print(f"[DEBUG] 原始名称: {name}, 生成唯一任务ID: {unique_task_id}")
        # ====================================================

        payload = {
            "image": image_url,
            "mode": "std",
            "sound_file": audio_url,
            "with_audio": True,
            "external_task_id": unique_task_id
        }

        if prompt and prompt != "string":
            payload["prompt"] = prompt
        
        # 注意：不再使用 name 作为 external_task_id
        # 如果前端传入了 name，可以记录到日志，但不作为任务ID使用

        payload = {k: v for k, v in payload.items() if v is not None}

        print(f"[DEBUG] 数字人请求URL: {url}")
        print(f"[DEBUG] 数字人请求参数: {payload}")
        response = requests.post(url, json=payload, headers=self._get_headers())
        result = response.json()
        print(f"[DEBUG] 数字人响应: {result}")

        if result.get("code") != 0:
            raise Exception(f"可灵数字人API错误: {result.get('message')}")

        return result["data"]["task_id"]
    
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(Exception))
    def get_digital_human_task_status(self, task_id: str) -> Dict:
        """查询数字人任务状态（带自动重试，遇到异常重试3次，每次间隔2秒）"""
        base_url = self._get_base_url()
        url = f"{base_url}/videos/avatar/image2video/{task_id}"
        response = requests.get(url, headers=self._get_headers())
        result = response.json()
        
        if result.get("code") != 0:
            raise Exception(f"查询数字人任务失败: {result.get('message')}")
        
        return result["data"]
    
    def wait_for_digital_human_result(self, task_id: str, max_wait: int = 900, 
                                       poll_interval: int = 15) -> Dict:
        """轮询等待数字人任务完成"""
        start_time = time.time()
        current_interval = poll_interval
        
        while time.time() - start_time < max_wait:
            try:
                status_data = self.get_digital_human_task_status(task_id)
                task_status = status_data.get("task_status")
                print(f"[DEBUG] 数字人任务状态: {task_status}")
                
                if task_status == "succeed":
                    task_result = status_data.get("task_result", {})
                    videos = task_result.get("videos", [])
                    if videos:
                        status_data["task_result"]["video_url"] = videos[0].get("url", "")
                    return status_data
                elif task_status == "failed":
                    error_msg = status_data.get("task_status_msg", "未知错误")
                    raise Exception(f"数字人任务失败: {error_msg}")
            except Exception as e:
                if "parallel task" in str(e).lower() or "1303" in str(e):
                    print(f"[DEBUG] 并发限制，稍后重试...")
                    time.sleep(current_interval * 2)
                    continue
                raise e
            
            time.sleep(current_interval)
            current_interval = min(current_interval + 5, 30)
        
        raise Exception(f"数字人任务超时，task_id: {task_id}")

    # ========== 音色列表接口 ==========
    def get_tts_voices(self) -> List[Dict]:
        """
        获取可灵 TTS 音色列表（预置音色）
        使用 GET /v1/general/presets-voices 接口
        支持分页获取所有音色
        """
        import requests
        
        base_url = self._get_base_url()
        headers = self._get_headers()
        
        all_voices = []
        page_num = 1
        page_size = 200  # 每次获取200条
        
        print(f"[DEBUG] 开始获取预置音色列表...")
        
        while True:
            url = f"{base_url}/general/presets-voices?pageNum={page_num}&pageSize={page_size}"
            print(f"[DEBUG] 请求第 {page_num} 页: {url}")
            
            try:
                response = requests.get(url, headers=headers, timeout=30)
                print(f"[DEBUG] 响应状态码: {response.status_code}")
                
                if response.status_code != 200:
                    print(f"[ERROR] 可灵 API 返回非200: {response.status_code}")
                    break
                
                result = response.json()
                print(f"[DEBUG] 可灵返回 code: {result.get('code')}")
                
                if result.get("code") != 0:
                    print(f"[ERROR] 可灵 API 错误: {result.get('message')}")
                    break
                
                data_list = result.get("data", [])
                print(f"[DEBUG] 第 {page_num} 页获取到 {len(data_list)} 条音色任务")
                
                if not data_list:
                    print(f"[DEBUG] 没有更多数据，停止获取")
                    break
                
                # 遍历每个任务，提取音色
                for item in data_list:
                    task_id = item.get("task_id")
                    task_result = item.get("task_result", {})
                    voices = task_result.get("voices", [])
                    
                    print(f"[DEBUG] 任务 {task_id} 包含 {len(voices)} 个音色")
                    
                    for voice in voices:
                        all_voices.append({
                            "id": voice.get("voice_id"),
                            "name": voice.get("voice_name"),
                            "preview_url": voice.get("trial_url"),
                            "language": voice.get("language", "zh-CN"),
                            "gender": voice.get("gender", "female"),
                            "type": "preset",
                            "owned_by": voice.get("owned_by", "kling")
                        })
                
                # 如果返回数据少于 pageSize，说明是最后一页
                if len(data_list) < page_size:
                    print(f"[DEBUG] 已获取全部数据，共 {len(data_list)} 条（小于 pageSize={page_size}）")
                    break
                
                page_num += 1
                
            except Exception as e:
                print(f"[ERROR] 获取预置音色异常: {e}")
                import traceback
                traceback.print_exc()
                break
        
        print(f"[DEBUG] ========== 获取完成 ==========")
        print(f"[DEBUG] 总共获取 {len(all_voices)} 个预置音色")
        
        if all_voices:
            # 打印前3个音色示例
            for i, voice in enumerate(all_voices[:3]):
                print(f"[DEBUG] 音色示例 {i+1}: {voice.get('name')} (ID: {voice.get('id')})")
        
        return all_voices if all_voices else self._get_mock_voices()

    # ========== 自定义音色列表接口 ==========
    def get_custom_voices(self, page_num: int = 1, page_size: int = 30) -> List[Dict]:
        """
        获取可灵自定义音色列表
        使用 GET /v1/general/custom-voices 接口
        """
        import requests
        
        base_url = self._get_base_url()
        url = f"{base_url}/general/custom-voices?pageNum={page_num}&pageSize={page_size}"
        headers = self._get_headers()
        
        print(f"[DEBUG] 请求自定义音色列表 URL: {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            print(f"[DEBUG] 响应状态码: {response.status_code}")
            
            if response.status_code != 200:
                print(f"[WARN] 获取自定义音色失败: {response.status_code}")
                return []
            
            result = response.json()
            
            if result.get("code") != 0:
                print(f"[WARN] 自定义音色 API 错误: {result.get('message')}")
                return []
            
            data_list = result.get("data", [])
            print(f"[DEBUG] 获取到 {len(data_list)} 条自定义音色记录")
            
            formatted_voices = []
            for item in data_list:
                if item.get("task_status") != "succeed":
                    continue
                task_result = item.get("task_result", {})
                voices = task_result.get("voices", [])
                for voice in voices:
                    formatted_voices.append({
                        "id": voice.get("voice_id"),
                        "name": voice.get("voice_name"),
                        "preview_url": voice.get("trial_url"),
                        "type": "custom",
                        "owned_by": voice.get("owned_by", "user")
                    })
            
            return formatted_voices
            
        except Exception as e:
            print(f"[ERROR] 获取自定义音色异常: {e}")
            return []

    # ========== 获取全部音色（预置+自定义） ==========
    def get_all_voices(self) -> List[Dict]:
        """获取全部音色：预置音色 + 自定义音色"""
        print(f"[DEBUG] ========== 开始获取全部音色 ==========")
        
        preset_voices = self.get_tts_voices()
        print(f"[DEBUG] 预置音色: {len(preset_voices)} 个")
        
        custom_voices = self.get_custom_voices()
        print(f"[DEBUG] 自定义音色: {len(custom_voices)} 个")
        
        # 合并列表，自定义音色放在前面
        all_voices = custom_voices + preset_voices
        
        print(f"[DEBUG] 总共获取 {len(all_voices)} 个音色")
        return all_voices

    def _get_mock_voices(self) -> List[Dict]:
        """模拟音色数据（降级用，当可灵 API 不可用时使用）"""
        return [
            {"id": "zh-CN-XiaoxiaoNeural", "name": "晓晓 - 温柔女声", "preview_url": "", "language": "zh-CN", "gender": "female", "type": "preset"},
            {"id": "zh-CN-YunxiNeural", "name": "云希 - 沉稳男声", "preview_url": "", "language": "zh-CN", "gender": "male", "type": "preset"},
            {"id": "zh-CN-XiaoyiNeural", "name": "晓伊 - 活泼女声", "preview_url": "", "language": "zh-CN", "gender": "female", "type": "preset"},
            {"id": "zh-CN-YunjianNeural", "name": "云健 - 磁性男声", "preview_url": "", "language": "zh-CN", "gender": "male", "type": "preset"},
        ]

# 单例实例
kling_service = KlingService()