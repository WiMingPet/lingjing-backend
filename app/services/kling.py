"""
可灵AI API 调用服务
"""
import requests
import jwt
import time
from datetime import datetime, timedelta
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
    
    def generate_image(self, prompt: str, negative_prompt: str = "", 
                       width: int = 512, height: int = 512) -> str:
        """文生图，返回 task_id"""
        base_url = self._get_base_url()
        url = f"{base_url}/images/generations"
        
        if width > height:
            aspect_ratio = "16:9"
        elif height > width:
            aspect_ratio = "9:16"
        else:
            aspect_ratio = "1:1"
        
        payload = {
            "model_name": "kling-v1",
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "aspect_ratio": aspect_ratio,
            "n": 1
        }
        
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
    
    # ========== 视频生成方法 ==========
    
    def generate_video(self, image_url: str, prompt: str = "", 
                       duration: int = 5, mode: str = "std") -> str:
        """图生视频，返回 task_id"""
        base_url = self._get_base_url()
        url = f"{base_url}/videos/image2video"
        
        payload = {
            "model_name": "kling-v2-5-turbo",
            "image": image_url,
            "prompt": prompt,
            "duration": str(duration),
            "mode": mode
        }
        
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
    
    # ========== 虚拟试穿方法 ==========
    
    def generate_tryon(self, model_image_url: str, garment_image_url: str, 
                       digital_human_id: str = None) -> str:
        """
        虚拟试穿 - 使用 kling-v1 模型
        """
        base_url = self._get_base_url()
        url = f"{base_url}/images/generations"
        
        prompt = "Virtual tryon: wear the garment from the second image on the person in the first image. Make the clothing fit naturally on the person."
        
        payload = {
            "model_name": "kling-v1",
            "prompt": prompt,
            "model_image": model_image_url,
            "garment_image": garment_image_url,
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
        url = f"{base_url}/images/generations/{task_id}"
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
    # ========== 多角度试穿方法（多图参考合成统一角色） ==========
    
    def multi_image_to_image(self, subject_images: List[str], 
                              prompt: str = "",
                              scene_image: str = None,
                              style_image: str = None) -> str:
        """
        多图参考生图（用于多角度合成统一角色）
        - subject_images: 用户上传的多张照片 URL 列表（2-4张）
        - prompt: 提示词
        - scene_image: 场景图片 URL（可选）
        - style_image: 风格图片 URL（可选）
        返回: task_id
        """
        base_url = self._get_base_url()
        url = f"{base_url}/images/multi-image2image"
        
        # 构建主体图片列表
        subject_list = [{"subject_image": img} for img in subject_images]
        
        payload = {
            "model_name": "kling-v2-1",
            "subject_image_list": subject_list,
            "prompt": prompt,
            "aspect_ratio": "1:1"
        }
        
        if scene_image:
            payload["scene_image"] = scene_image
        if style_image:
            payload["style_image"] = style_image
        
        print(f"[DEBUG] 多图参考请求URL: {url}")
        print(f"[DEBUG] 多图参考请求参数: {payload}")
        response = requests.post(url, json=payload, headers=self._get_headers())
        result = response.json()
        print(f"[DEBUG] 多图参考响应: {result}")
        
        if result.get("code") != 0:
            raise Exception(f"可灵多图参考API错误: {result.get('message')}")
        
        return result["data"]["task_id"]
    
    def get_multi_image_task_status(self, task_id: str) -> Dict:
        """查询多图参考任务状态"""
        base_url = self._get_base_url()
        url = f"{base_url}/images/multi-image2image/{task_id}"
        response = requests.get(url, headers=self._get_headers())
        result = response.json()
        
        if result.get("code") != 0:
            raise Exception(f"查询多图参考任务失败: {result.get('message')}")
        
        return result["data"]
    
    def wait_for_multi_image_result(self, task_id: str, max_wait: int = 120, 
                                     poll_interval: int = 3) -> Dict:
        """轮询等待多图参考任务完成"""
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            status_data = self.get_multi_image_task_status(task_id)
            task_status = status_data.get("task_status")
            print(f"[DEBUG] 多图参考任务状态: {task_status}")
            
            if task_status == "succeed":
                return status_data
            elif task_status == "failed":
                error_msg = status_data.get("task_status_msg", "未知错误")
                raise Exception(f"多图参考任务失败: {error_msg}")
            
            time.sleep(poll_interval)
        
        raise Exception(f"多图参考任务超时，task_id: {task_id}")


# 单例实例
kling_service = KlingService()