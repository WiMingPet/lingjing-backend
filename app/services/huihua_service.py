"""
绘蛙 AI 口播带货视频服务
阿里云市场 API
"""
import os
import uuid
import time
import json
import requests
from typing import List, Dict


class HuihuaService:

    def __init__(self):
        self.appcode = os.getenv("HUIHUA_APPCODE", "")
        self.base_url = "https://aigenvideo.market.alicloudapi.com/aliyun/marketplace/api"
        if not self.appcode:
            print("[HUIHUA] ⚠️ 未配置 HUIHUA_APPCODE")

    def _headers(self) -> Dict:
        return {
            "Authorization": f"APPCODE {self.appcode}",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Ca-Nonce": str(uuid.uuid4()),   # ★ 每次请求不同
        }

    def generate_video(
        self,
        item_image_urls: List[str],
        item_description: str,
        ratio: str = "16:9",
        resolution: str = "1080",
        output_language: str = "zh",
        enable_voiceover: bool = True,
        enable_subtitle: bool = True,
        duration: int = 15,
    ) -> str:
        """
        提交绘蛙视频生成任务
        返回 taskId
        """
        url = f"{self.base_url}/gen_video"

        # itemImages 是 JSON 字符串
        item_images = [{"originalImageUrl": u} for u in item_image_urls]
        item_images_str = json.dumps(item_images, ensure_ascii=False)

        # form-urlencoded 的所有值必须转字符串
        payload = {
            "itemImages": item_images_str,
            "itemDescription": item_description,
            "ratio": ratio,
            "resolution": resolution,
            "outputLanguage": output_language,
            "enableVoiceover": "true" if enable_voiceover else "false",
            "enableSubtitle": "true" if enable_subtitle else "false",
            "duration": str(duration),
        }

        print(f"[HUIHUA] 提交任务: {item_images_str[:200]} | desc: {item_description[:100]}")

        resp = requests.post(url, data=payload, headers=self._headers(), timeout=60)
        print(f"[HUIHUA] 状态码: {resp.status_code}")
        print(f"[HUIHUA] 响应: {resp.text[:500]}")

        if resp.status_code != 200:
            raise Exception(f"绘蛙 API 错误: {resp.status_code} {resp.text[:300]}")

        result = resp.json()
        task_id = (
            result.get("data", {}).get("taskId")
            or result.get("taskId")
            or result.get("data", {}).get("task_id")
        )
        if not task_id:
            raise Exception(f"绘蛙未返回 taskId: {result}")

        return str(task_id)

    def query_video(self, task_id: str) -> Dict:
        url = f"{self.base_url}/query_videos"
        headers = {
            "Authorization": f"APPCODE {self.appcode}",
            "X-Ca-Nonce": str(uuid.uuid4()),
        }
        resp = requests.get(url, headers=headers, params={"taskId": task_id}, timeout=30)

        # 403 限流，下次再查
        if resp.status_code == 403:
            return {"status": "processing", "video_url": "", "error": ""}
        if resp.status_code != 200:
            raise Exception(f"绘蛙查询错误: {resp.status_code}")

        result = resp.json()
        video_infos = result.get("videoInfos") or []
        if not video_infos:
            return {"status": "processing", "video_url": "", "error": ""}

        v = video_infos[0]
        status_value = v.get("statusValue")

        if status_value == 4:
            return {
                "status": "succeeded",
                "video_url": v.get("videoUrl") or "",
                "cover_url": v.get("coverUrl") or "",
                "duration": v.get("duration") or 0,
                "error": "",
            }
        elif status_value == 3:
            return {
                "status": "failed",
                "video_url": "",
                "error": result.get("reason") or "生成失败",
            }
        else:
            return {"status": "processing", "video_url": "", "error": ""}

    def wait_for_result(self, task_id: str, max_wait: int = 1800, poll_interval: int = 30) -> Dict:
        """轮询等待，间隔 30 秒（避免 403 限流）"""
        start = time.time()
        while time.time() - start < max_wait:
            try:
                r = self.query_video(task_id)
                if r["status"] == "succeeded":
                    return r
                elif r["status"] == "failed":
                    raise Exception(f"绘蛙生成失败: {r['error']}")
            except Exception as e:
                if "失败" in str(e):
                    raise e
                print(f"[HUIHUA] 查询异常，继续轮询: {e}")
            time.sleep(poll_interval)
        raise Exception(f"绘蛙任务超时: {task_id}")


huihua_service = HuihuaService()