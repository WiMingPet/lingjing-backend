"""
可灵AI API 调用服务 - Kling 3.0 + Bearer Token 认证
"""
import requests
import time
from typing import Dict, Optional, List
from app.config import settings
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

def enhance_prompt(prompt: str, model: str = "2.6", sound: str = "off") -> str:
    """
    增强提示词，提升动作精准度
    - 用户没写：不干预
    - 用户写了：只补充缺失的信息
    """
    if not prompt or not prompt.strip():
        return ""  # 不干预，让可灵自由发挥
    
    prompt = prompt.strip()
    
    # ========== 1. 动作类：补充节奏描述 ==========
    action_keywords = [
        "转身", "走动", "跳舞", "挥手", "跑", "跳", "蹲", "坐", "躺",
        "微笑", "点头", "摇头", "抬手", "伸手", "举手",
        "展示", "拿着", "举起", "放下", "看镜头", "看向", "注视"
    ]
    if any(word in prompt for word in action_keywords):
        if "缓慢" not in prompt and "自然" not in prompt and "快速" not in prompt:
            prompt += "，动作流畅自然"
    
    # ========== 2. 说话类：补充口型同步（仅3.0有声） ==========
    if model == "3.0" and sound == "native":
        if ("说" in prompt or "唱" in prompt) and "口型" not in prompt:
            prompt += "，口型与语音同步"
    
    return prompt

class KlingService:
    """可灵AI API 服务"""
    
    def __init__(self):
        self.api_url = settings.KLING_API_URL
        self.api_key = settings.KLING_API_KEY
    
    def _get_headers(self) -> Dict:
        """获取请求头 - Bearer Token 方式"""
        return {
            "Authorization": f"Bearer {self.api_key}",
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
        - 有 reference_image_url: 图生图（使用 Omni 模型，人物还原效果好）
        - 无 reference_image_url: 文生图（使用 kling-v3）
        返回 task_id
        """
        base_url = self._get_base_url()
        
        # ========== 有参考图：使用 Omni 模型 ==========
        if reference_image_url:
            url = f"{base_url}/images/omni-image"
            
            payload = {
                "model_name": "kling-v3-omni",
                "prompt": prompt if prompt else "保持原图不变，保留人物面部特征、五官、发型、服装细节",
                "image_list": [
                    {"image": reference_image_url}
                ],
                "resolution": "2k",
                "n": num_images,
                "aspect_ratio": "1:1"
            }
            print(f"[DEBUG] 使用 Omni 模型图生图（人物保留增强）")
            print(f"[DEBUG] 参考图: {reference_image_url}")
        
        # ========== 无参考图：使用 kling-v3 文生图 ==========
        else:
            url = f"{base_url}/images/generations"
            
            # 计算宽高比
            if width > height:
                aspect_ratio = "16:9"
            elif height > width:
                aspect_ratio = "9:16"
            else:
                aspect_ratio = "1:1"
            
            payload = {
                "model_name": "kling-v3",
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "aspect_ratio": aspect_ratio,
                "n": num_images,
                "resolution": "2k"
            }
            print(f"[DEBUG] 使用 kling-v3 文生图")
        
        print(f"[DEBUG] 请求URL: {url}")
        print(f"[DEBUG] 请求参数: {payload}")
        response = requests.post(url, json=payload, headers=self._get_headers(), timeout=30)
        result = response.json()
        print(f"[DEBUG] 响应状态码: {response.status_code}")
        print(f"[DEBUG] 响应内容: {response.text}")
        
        if result.get("code") != 0:
            raise Exception(f"可灵API错误: {result.get('message')}")
        
        return result["data"]["task_id"]
    
    def get_task_status(self, task_id: str) -> Dict:
        """查询图片任务状态（兼容 omni-image 和 generations 端点）"""
        base_url = self._get_base_url()
        
        # 先尝试 omni-image 端点
        url = f"{base_url}/images/omni-image/{task_id}"
        print(f"[DEBUG] 查询 omni-image 任务: {url}")
        response = requests.get(url, headers=self._get_headers(), timeout=30)
        result = response.json()
        
        # 如果 omni-image 查询失败（404），尝试 generations 端点
        if result.get("code") != 0:
            url = f"{base_url}/images/generations/{task_id}"
            print(f"[DEBUG] omni-image 查询失败，尝试 generations: {url}")
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            result = response.json()
        
        print(f"[DEBUG] 任务状态响应: {result}")
        
        if result.get("code") != 0:
            raise Exception(f"查询失败: {result.get('message')}")
        
        return result["data"]
    
    def wait_for_result(self, task_id: str, task_type: str = "image", 
                        max_wait: int = 300, poll_interval: int = 2) -> Dict:
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
    
    def generate_image_o1(self, prompt: str, image_urls: list,
                          resolution: str = "2k", aspect_ratio: str = "1:1",
                          n: int = 1) -> str:
        """
        可灵图片O1 - 多模态图像编辑/生成
        用自然语言描述哪里要改、哪里不变，无需手动mask
        返回 task_id
        """
        import time as _time

        base_url = self._get_base_url()
        url = f"{base_url}/images/omni-image"

        # ========== 根据原图比例动态设置 aspect_ratio ==========
        try:
            from PIL import Image as _PILImage
            from io import BytesIO as _BytesIO
            _resp = requests.get(image_urls[0], timeout=30)
            _img = _PILImage.open(_BytesIO(_resp.content))
            _w, _h = _img.size
            _ratio = _w / _h
            if _ratio > 1.2:
                aspect_ratio = "16:9"
            elif _ratio < 0.8:
                aspect_ratio = "9:16"
            else:
                aspect_ratio = "1:1"
            print(f"[KLING-O1] 动态比例: {aspect_ratio} (原图 {_w}x{_h})")
        except Exception as e:
            print(f"[KLING-O1] 计算比例失败，用默认 1:1: {e}")
        # ====================================================

        payload = {
            "model_name": "kling-image-o1",
            "prompt": prompt,
            "image_list": [
                {"image": img_url} for img_url in image_urls
            ],
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "n": n,
        }

        print(f"[KLING-O1] 提交图片O1任务")
        print(f"[KLING-O1] prompt: {prompt[:100]}...")
        print(f"[KLING-O1] 参考图数量: {len(image_urls)}")

        response = requests.post(url, json=payload,
                                 headers=self._get_headers(), timeout=30)
        result = response.json()

        if result.get("code") != 0:
            msg = result.get("message", "未知错误")
            # 并发限制重试
            if "parallel" in msg.lower() or result.get("code") == 1303:
                max_retries = 3
                for attempt in range(1, max_retries + 1):
                    wait = attempt * 15
                    print(f"[KLING-O1] 并发限制，{wait}s 后重试 ({attempt}/{max_retries})")
                    _time.sleep(wait)
                    response = requests.post(url, json=payload,
                                             headers=self._get_headers(), timeout=30)
                    result = response.json()
                    if result.get("code") == 0:
                        break
                else:
                    raise Exception(f"可灵O1并发限制重试失败: {msg}")
            else:
                raise Exception(f"可灵O1 API错误: {msg}")

        task_id = result["data"]["task_id"]
        print(f"[KLING-O1] 任务已提交: {task_id}")
        return task_id

    def wait_for_o1_result(self, task_id: str, max_wait: int = 600,
                           poll_interval: int = 10) -> Dict:
        """
        轮询等待图片O1任务完成
        max_wait=600秒（10分钟）
        """
        import time as _time

        base_url = self._get_base_url()
        url = f"{base_url}/images/omni-image/{task_id}"

        start_time = _time.time()
        last_status = None

        while _time.time() - start_time < max_wait:
            elapsed = int(_time.time() - start_time)
            try:
                response = requests.get(url, headers=self._get_headers(), timeout=30)
                result = response.json()

                if result.get("code") != 0:
                    print(f"[KLING-O1] 查询异常: {result.get('message')}")
                    _time.sleep(poll_interval)
                    continue

                data = result.get("data", {})
                task_status = data.get("task_status")
                last_status = task_status

                print(f"[KLING-O1] 状态: {task_status}, elapsed={elapsed}s")

                if task_status == "succeed":
                    task_result = data.get("task_result", {})
                    images = task_result.get("images", [])
                    if images:
                        data["output_url"] = images[0].get("url", "")
                    return data

                elif task_status == "failed":
                    error_msg = data.get("task_status_msg", "未知错误")
                    raise Exception(f"图片O1任务失败: {error_msg}")

            except Exception as e:
                if "失败" in str(e):
                    raise e
                print(f"[KLING-O1] 查询异常，继续轮询: {e}")

            _time.sleep(poll_interval)

        # 超时前再查一次终态
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            result = response.json()
            data = result.get("data", {})
            if data.get("task_status") == "succeed":
                task_result = data.get("task_result", {})
                images = task_result.get("images", [])
                if images:
                    data["output_url"] = images[0].get("url", "")
                print(f"[KLING-O1] 超时复查发现已成功: {task_id}")
                return data
        except Exception as e:
            print(f"[KLING-O1] 超时复查异常: {e}")

        raise Exception(f"图片O1任务超时，task_id={task_id}, 最后状态={last_status}")

    # ========== 视频生成（图生视频）==========
    def generate_video(self, image_url: str = None, prompt: str = "", 
                       duration: int = 5, mode: str = "std",
                       model: str = "2.6", sound: str = "off") -> str:
        """
        视频生成 - 支持2.6基础版和3.0增强版
        - model: '2.6' 或 '3.0'
        - sound: 'off' 或 'native'（仅3.0支持native）
        - duration: 5, 10（2.6）；5, 10, 15（3.0）
        """
        # ========== 修复：新版API不需要 /v1 前缀 ==========
        base_url = self.api_url.rstrip('/')
        if base_url.endswith('/v1'):
            base_url = base_url[:-3]  # 移除末尾的 /v1
        # ==================================================
        
        # 根据模型选择API端点
        if model == "3.0":
            url = f"{base_url}/image-to-video/kling-3.0"
            print(f"[DEBUG] 使用3.0增强版 API")
        else:
            url = f"{base_url}/image-to-video/kling-2.6"
            print(f"[DEBUG] 使用2.6基础版 API")
        
        # ========== 增强提示词 ==========
        enhanced_prompt = enhance_prompt(prompt, model=model, sound=sound)
        print(f"[DEBUG] 原始提示词: {prompt}")
        print(f"[DEBUG] 增强后提示词: {enhanced_prompt}")
        # ==============================
        
        # 构建请求参数（新版API格式）
        payload = {
            "contents": [
                {
                    "type": "prompt",
                    "text": enhanced_prompt
                },
                {
                    "type": "first_frame",
                    "url": image_url
                }
            ],
            "settings": {
                "resolution": "720p",
                "duration": duration,
                "audio": sound if model == "3.0" else "off",
            },
            "options": {
                "watermark_info": {
                    "enabled": False
                }
            }
        }
        
        # 3.0模型需要multi_shot参数
        if model == "3.0":
            payload["settings"]["multi_shot"] = False
        
        print(f"[DEBUG] 视频生成请求URL: {url}")
        print(f"[DEBUG] 视频生成请求参数: {payload}")
        
        response = requests.post(url, json=payload, headers=self._get_headers(), timeout=30)
        result = response.json()
        print(f"[DEBUG] 视频生成响应状态码: {response.status_code}")
        print(f"[DEBUG] 视频生成响应: {result}")
        
        if result.get("code") != 0:
            raise Exception(f"视频API错误: {result.get('message')}")
        
        return result["data"]["id"]
    
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(Exception))
    def get_video_task_status(self, task_id: str) -> Dict:
        """查询视频任务状态（带重试）- 新版API"""
        # ========== 修复：新版API不需要 /v1 前缀 ==========
        base_url = self.api_url.rstrip('/')
        if base_url.endswith('/v1'):
            base_url = base_url[:-3]  # 移除末尾的 /v1
        # ==================================================
        
        url = f"{base_url}/tasks"
        
        # 新版API使用查询参数
        params = {"task_ids": task_id}
        
        print(f"[DEBUG] 查询视频任务URL: {url}")
        print(f"[DEBUG] 查询参数: {params}")
        
        response = requests.get(url, headers=self._get_headers(), params=params, timeout=30)
        result = response.json()
        print(f"[DEBUG] 查询视频任务响应: {result}")
        
        if result.get("code") != 0:
            raise Exception(f"查询视频任务失败: {result.get('message')}")
        
        # 新版API返回 data 是列表
        data_list = result.get("data", [])
        if not data_list:
            raise Exception("查询视频任务失败: 无数据")
        
        task_data = data_list[0]
        
        # 转换为旧格式兼容
        task_status = task_data.get("status")
        # 新版状态: submitted, processing, succeeded, failed
        # 旧版状态: submitted, processing, succeed, failed
        status_mapping = {
            "succeeded": "succeed",
            "submitted": "submitted",
            "processing": "processing",
            "failed": "failed"
        }
        
        formatted_data = {
            "task_status": status_mapping.get(task_status, task_status),
            "task_status_msg": task_data.get("message", ""),
            "task_result": {}
        }
        
        # 提取视频URL
        outputs = task_data.get("outputs", [])
        for output in outputs:
            if output.get("type") == "video":
                formatted_data["task_result"]["videos"] = [{"url": output.get("url", "")}]
                break
        
        return formatted_data
    
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

    def generate_tryon_video(self, image_url: str = None, prompt: str = "", 
                            duration: int = 5, mode: str = "std",
                            model: str = "3.0", sound: str = "off") -> str:
        """
        试穿视频生成 - 使用新版API
        - 默认用3.0增强版（保证颜色效果）
        """
        # 新版API不需要 /v1
        base_url = self.api_url.rstrip('/')
        if base_url.endswith('/v1'):
            base_url = base_url[:-3]
        
        # 根据模型选择端点
        if model == "3.0":
            url = f"{base_url}/image-to-video/kling-3.0"
            print(f"[DEBUG] 试穿视频使用3.0增强版 API")
        else:
            url = f"{base_url}/image-to-video/kling-2.6"
            print(f"[DEBUG] 试穿视频使用2.6基础版 API")
        
        # 新版API参数格式
        payload = {
            "contents": [
                {
                    "type": "prompt",
                    "text": prompt
                },
                {
                    "type": "first_frame",
                    "url": image_url
                }
            ],
            "settings": {
                "resolution": "720p",
                "duration": duration,
                "audio": sound if model == "3.0" else "off",
            },
            "options": {
                "watermark_info": {
                    "enabled": False
                }
            }
        }
        
        # 3.0需要multi_shot参数
        if model == "3.0":
            payload["settings"]["multi_shot"] = False
        
        print(f"[DEBUG] 试穿视频请求URL: {url}")
        print(f"[DEBUG] 试穿视频请求参数: {payload}")
        
        response = requests.post(url, json=payload, headers=self._get_headers(), timeout=30)
        result = response.json()
        print(f"[DEBUG] 试穿视频响应: {result}")
        
        if result.get("code") != 0:
            raise Exception(f"试穿视频API错误: {result.get('message')}")
        
        return result["data"]["id"]
    
    # ========== 虚拟试穿（独立API）==========
    def generate_tryon(self, human_image_url: str, cloth_image_url: str, cloth_category: str = None, digital_human_id: str = None) -> str:
        base_url = self._get_base_url()
        url = f"{base_url}/images/omni-image"
        
        prompt = "给<<image_1>>中的模特穿上<<image_2>>中的服装，配饰的细节如：图案，款式保持不变，保持模特的姿势和背景不变，专业电商试穿效果"
        
        payload = {
            "model_name": "kling-v3-omni",
            "prompt": prompt,
            "image_list": [
                {"image": human_image_url},    # image_1 = 模特
                {"image": cloth_image_url}     # image_2 = 服装
            ],
            "resolution": "2k",
            "aspect_ratio": "1:1",
            "n": 1
        }
        
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
        url = f"{base_url}/images/omni-image/{task_id}"
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
    
    def generate_talking_agent(self, request_data: dict) -> dict:
        """
        口播带货 - 调用可灵 /solutions/talking_agent
        支持达人口播和口播带货两种模式
        """
        import time
        
        base_url = self.api_url.rstrip('/')
        if base_url.endswith('/v1'):
            base_url = base_url[:-3]
        
        url = f"{base_url}/solutions/talking_agent"
        
        # 构建 contents
        contents = []
        
        # 人物来源
        if request_data.get("avatar_image_url"):
            contents.append({
                "type": "avatar_image",
                "url": request_data["avatar_image_url"]
            })
        elif request_data.get("avatar_id"):
            contents.append({
                "type": "avatar_id",
                "text": request_data["avatar_id"]
            })
        
        # 商品信息
        if request_data.get("product_images"):
            for img_url in request_data["product_images"]:
                contents.append({
                    "type": "ref_image",
                    "url": img_url
                })
        
        if request_data.get("goods_title"):
            contents.append({
                "type": "goods_title",
                "text": request_data["goods_title"]
            })
        
        if request_data.get("goods_price"):
            contents.append({
                "type": "goods_price",
                "text": request_data["goods_price"]
            })
        
        if request_data.get("target_audience"):
            contents.append({
                "type": "goods_target_audience",
                "text": request_data["target_audience"]
            })
        
        if request_data.get("selling_point"):
            contents.append({
                "type": "goods_selling_point",
                "text": request_data["selling_point"]
            })
        
        # 口播稿
        contents.append({
            "type": "speech_script",
            "text": request_data["script"]
        })
        
        # 构建 settings
        settings = {
            "resolution": request_data.get("resolution", "720p"),
            "aspect_ratio": request_data.get("aspect_ratio", "9:16"),
            "allow_polish": request_data.get("allow_polish", False),
        }
        
        # 上传人物图时，必须传 voice_id
        if request_data.get("avatar_image_url"):
            settings["voice_id"] = request_data.get("voice_id", "male_calm_informative")
        
        # 口播带货模式：不支持 speech_rate
        has_product = bool(request_data.get("product_images"))
        if not has_product and request_data.get("speech_rate"):
            settings["speech_rate"] = request_data["speech_rate"]
        
        payload = {
            "contents": contents,
            "settings": settings,
        }
        
        print(f"[DEBUG] 口播带货请求URL: {url}")
        print(f"[DEBUG] 口播带货请求参数: {payload}")
        
        response = requests.post(url, json=payload, headers=self._get_headers(), timeout=30)
        result = response.json()
        print(f"[DEBUG] 口播带货响应: {result}")
        
        if result.get("code") != 0:
            raise Exception(f"口播带货API错误: {result.get('message')}")
        
        data = result["data"]
        task_id = data.get("task_id") or data.get("id")
        print(f"[DEBUG] 口播带货任务ID: {task_id}")
        
        # 轮询等待
        return self._wait_for_talking_agent(task_id)
    
    def _wait_for_talking_agent(self, task_id: str, max_wait: int = 900, poll_interval: int = 10) -> dict:
        """轮询等待口播带货任务完成"""
        import time

        base_url = self.api_url.rstrip('/')
        if base_url.endswith('/v1'):
            base_url = base_url[:-3]

        start_time = time.time()

        while time.time() - start_time < max_wait:
            url = f"{base_url}/solutions"
            params = {"task_ids": task_id}

            response = requests.get(url, headers=self._get_headers(), params=params, timeout=30)
            result = response.json()

            if result.get("code") != 0:
                raise Exception(f"查询口播任务失败: {result.get('message')}")

            data = result.get("data", [])
            if not data:
                time.sleep(poll_interval)
                continue

            # 兼容 data 是列表或字典
            if isinstance(data, list):
                task_data = data[0]
            else:
                task_data = data

            status = task_data.get("status")
            print(f"[DEBUG] 口播任务状态: {status}")

            if status in ("succeeded", "succeed"):
                outputs = task_data.get("outputs", [])
                for output in outputs:
                    if output.get("type") == "video":
                        duration = output.get("duration", 0)
                        try:
                            duration = float(duration)
                        except (ValueError, TypeError):
                            duration = 0
                        return {
                            "video_url": output.get("url"),
                            "duration": duration
                        }
                return {"video_url": None, "duration": 0}
            elif status == "failed":
                raise Exception(f"口播任务失败: {task_data.get('message', '未知错误')}")

            time.sleep(poll_interval)

        raise Exception(f"口播任务超时: {task_id}")

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

        payload = {k: v for k, v in payload.items() if v is not None}

        # ========== 提交阶段对并发限制重试 ==========
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            print(f"[DEBUG] 数字人请求URL: {url}")
            print(f"[DEBUG] 数字人请求参数: {payload}, 第{attempt}次尝试")
            response = requests.post(url, json=payload, headers=self._get_headers())
            result = response.json()
            print(f"[DEBUG] 数字人响应: {result}")

            if result.get("code") == 0:
                return result["data"]["task_id"]

            msg = str(result.get("message", ""))
            code = result.get("code")

            # 并发限制，等待后重试
            if code == 1303 or "parallel task" in msg.lower():
                if attempt < max_retries:
                    wait = attempt * 10  # 10s, 20s, 30s, 40s
                    print(f"[DEBUG] 提交遇并发限制，{wait}s 后重试 (第{attempt}次): {msg}")
                    time.sleep(wait)
                    continue
                raise Exception(f"可灵数字人API错误(并发限制重试{max_retries}次仍失败): {msg}")

            # 其他错误直接抛出
            raise Exception(f"可灵数字人API错误: {msg}")
        # ============================================

        raise Exception("可灵数字人API错误: 未知原因")
    
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

    def wait_for_digital_human_result(self, task_id: str, max_wait: int = 1500,
                                       poll_interval: int = 15) -> Dict:
        """
        轮询等待数字人任务完成。
        max_wait=1500 秒（25 分钟）：可灵实测约 15.7 分钟，留高峰排队余量。
        超时前会再查一次终态，避免把已成功的任务误判为超时。
        """
        start_time = time.time()
        current_interval = poll_interval
        last_status = None
        last_msg = ""

        while time.time() - start_time < max_wait:
            elapsed = int(time.time() - start_time)
            status_data = None
            try:
                status_data = self.get_digital_human_task_status(task_id)
            except Exception as e:
                if "parallel task" in str(e).lower() or "1303" in str(e):
                    print(f"[DEBUG] 并发限制，稍后重试...")
                    time.sleep(current_interval * 2)
                    continue
                # 只有查询接口本身的异常才继续轮询
                print(f"[DEBUG] 查询异常，继续轮询: {e}")
                time.sleep(current_interval)
                current_interval = min(current_interval + 5, 30)
                continue

            task_status = status_data.get("task_status")
            last_status = task_status
            last_msg = status_data.get("task_status_msg", "")
            print(f"[DEBUG] 数字人任务状态: {task_status}, elapsed={elapsed}s")

            if task_status == "succeed":
                task_result = status_data.get("task_result", {})
                videos = task_result.get("videos", [])
                if videos:
                    status_data["task_result"]["video_url"] = videos[0].get("url", "")
                return status_data
            elif task_status == "failed":
                # 业务失败，直接抛出，不被下面的 except 捕获
                raise Exception(f"数字人任务失败: {status_data.get('task_status_msg', '未知错误')}")

            time.sleep(current_interval)
            current_interval = min(current_interval + 5, 30)

        # ========== 超时前再查一次终态，避免误判 ==========
        try:
            status_data = self.get_digital_human_task_status(task_id)
            final_status = status_data.get("task_status")
            last_status = final_status
            last_msg = status_data.get("task_status_msg", "")
            print(f"[DEBUG] 超时后复查: status={final_status}, msg={last_msg}")

            if final_status == "succeed":
                task_result = status_data.get("task_result", {})
                videos = task_result.get("videos", [])
                if videos:
                    status_data["task_result"]["video_url"] = videos[0].get("url", "")
                print(f"[DEBUG] 超时复查发现任务已成功，返回结果: task_id={task_id}")
                return status_data
        except Exception as e:
            print(f"[DEBUG] 超时复查异常: {e}")

        raise Exception(
            f"数字人任务超时，task_id: {task_id}, "
            f"elapsed={int(time.time() - start_time)}s, "
            f"最后状态={last_status}, msg={last_msg}"
        )

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