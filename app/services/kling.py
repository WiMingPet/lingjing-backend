"""
可灵AI API 调用服务 - 基于官方文档一次性修复
"""
import requests
import jwt
import time
from typing import Dict, Optional, List
from app.config import settings


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
            "mode": mode
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
    
    def get_video_task_status(self, task_id: str) -> Dict:
        """查询视频任务状态"""
        base_url = self._get_base_url()
        url = f"{base_url}/videos/image2video/{task_id}"
        response = requests.get(url, headers=self._get_headers())
        result = response.json()
        
        if result.get("code") != 0:
            raise Exception(f"查询视频任务失败: {result.get('message')}")
        
        return result["data"]
    
    def wait_for_video_result(self, task_id: str, max_wait: int = 300, 
                              poll_interval: int = 5) -> Dict:
        """轮询等待视频任务完成"""
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
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
            
            time.sleep(poll_interval)
        
        raise Exception(f"视频任务超时，task_id: {task_id}")
    
    # ========== 虚拟试穿（独立API）==========
    def generate_tryon(self, human_image_url: str, cloth_image_url: str, digital_human_id: str = None) -> str:
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
    
    def wait_for_tryon_result(self, task_id: str, max_wait: int = 120, 
                              poll_interval: int = 3) -> Dict:
        """轮询等待虚拟试穿任务完成"""
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            status_data = self.get_tryon_task_status(task_id)
            task_status = status_data.get("task_status")
            print(f"[DEBUG] 虚拟试穿任务状态: {task_status}")
            
            if task_status == "succeed":
                return status_data
            elif task_status == "failed":
                error_msg = status_data.get("task_status_msg", "未知错误")
                raise Exception(f"虚拟试穿任务失败: {error_msg}")
            
            time.sleep(poll_interval)
        
        raise Exception(f"虚拟试穿任务超时，task_id: {task_id}")
    
    # ========== 数字人分身 ==========
    def generate_digital_human(self, image_url: str, audio_url: str, prompt: str = None, name: str = None) -> str:
        """
        数字人分身 - 单张照片+音频生成视频
        使用可灵虚拟形象 API
        
        Args:
            image_url: 人物照片 URL
            audio_url: 音频文件 URL
            prompt: 提示词，控制情绪、表情、语速
            name: 数字人名称
        
        Returns:
            task_id
        """
        base_url = self._get_base_url()
        url = f"{base_url}/avatar/generations"
        
        payload = {
            "image": image_url,
            "audio": audio_url
        }
        if prompt:
            payload["prompt"] = prompt
        if name:
            payload["name"] = name
        
        print(f"[DEBUG] 数字人请求URL: {url}")
        print(f"[DEBUG] 数字人请求参数: {payload}")
        response = requests.post(url, json=payload, headers=self._get_headers())
        result = response.json()
        print(f"[DEBUG] 数字人响应: {result}")
        
        if result.get("code") != 0:
            raise Exception(f"可灵数字人API错误: {result.get('message')}")
        
        return result["data"]["task_id"]
    
    def get_digital_human_task_status(self, task_id: str) -> Dict:
        """查询数字人任务状态"""
        base_url = self._get_base_url()
        url = f"{base_url}/avatar/generations/{task_id}"
        response = requests.get(url, headers=self._get_headers())
        result = response.json()
        
        if result.get("code") != 0:
            raise Exception(f"查询数字人任务失败: {result.get('message')}")
        
        return result["data"]
    
    def wait_for_digital_human_result(self, task_id: str, max_wait: int = 300, 
                                       poll_interval: int = 5) -> Dict:
        """轮询等待数字人任务完成"""
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            status_data = self.get_digital_human_task_status(task_id)
            task_status = status_data.get("task_status")
            print(f"[DEBUG] 数字人任务状态: {task_status}")
            
            if task_status == "succeed":
                # 提取视频 URL
                task_result = status_data.get("task_result", {})
                videos = task_result.get("videos", [])
                if videos:
                    status_data["task_result"]["video_url"] = videos[0].get("url", "")
                return status_data
            elif task_status == "failed":
                error_msg = status_data.get("task_status_msg", "未知错误")
                raise Exception(f"数字人任务失败: {error_msg}")
            
            time.sleep(poll_interval)
        
        raise Exception(f"数字人任务超时，task_id: {task_id}")


# 单例实例
kling_service = KlingService()