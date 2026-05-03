import requests
import json
import time
import sys
import os

# --- 请将以下配置替换为你自己的 ---
# ======================================================
KLING_API_URL = "https://api-beijing.klingai.com"
YOUR_ACCESS_KEY = "ACBD8k4dG8HarmLtY9hFFDACfLnCmGYE"
YOUR_SECRET_KEY = "rG3JJgbFyRaDK3kyyDmgtMTtMBQgDKye"
# 你的后端项目路径，你需要用到里面的JWT生成函数
PROJECT_ROOT = r"C:\lingjing-backend-temp"
# ======================================================

# 将你的后端项目路径加入系统路径，以便正确导入
sys.path.append(PROJECT_ROOT)
os.environ.setdefault('KLING_API_KEY', YOUR_ACCESS_KEY)  # 为配置加载做准备
os.environ.setdefault('KLING_API_SECRET', YOUR_SECRET_KEY)

from app.config import settings
from app.services.kling import KlingService

kling = KlingService()

# 1. 在这里定义你要创建的5个新音色
#    请替换 OSS_URL 为你上一步上传音频文件后的真实地址
NEW_VOICES = [
    {"name": "知性学姐", "voice_url": "https://media.lingjing-media.com/custom-voices/%E7%9F%A5%E6%80%A7%E5%AD%A6%E5%A7%90.mp3"},
    {"name": "温雅老师", "voice_url": "https://media.lingjing-media.com/custom-voices/%E6%B8%A9%E9%9B%85%E8%80%81%E5%B8%88.mp3"},
    {"name": "活力男声", "voice_url": "https://media.lingjing-media.com/custom-voices/%E6%B4%BB%E5%8A%9B%E7%94%B7%E5%A3%B0.mp3"},
    {"name": "磁性大叔", "voice_url": "https://media.lingjing-media.com/custom-voices/%E7%A3%81%E6%80%A7%E5%A4%A7%E5%8F%94.mp3"},
    {"name": "温柔解说", "voice_url": "https://media.lingjing-media.com/custom-voices/%E6%B8%A9%E6%9F%94%E8%A7%A3%E8%AF%B4.mp3"},
]

def create_custom_voice(voice_name, audio_url):
    """调用可灵API创建自定义音色，并轮询等待任务完成，返回voice_id和preview_url"""
    # 提交自定义音色创建任务
    url = f"{KLING_API_URL}/v1/general/custom-voices"
    headers = kling._get_headers()  # 复用你已有的JWT生成逻辑
    payload = {
        "voice_name": voice_name,
        "voice_url": audio_url,
        "external_task_id": f"lingjing_{voice_name}_{int(time.time())}"
    }
    
    print(f"🚀 正在创建音色: {voice_name}...")
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        print(f"❌ 任务提交失败: {response.text}")
        return None, None
    
    task_id = response.json().get("data", {}).get("task_id")
    if not task_id:
        print(f"❌ 未获取到 task_id: {response.text}")
        return None, None
    
    # 轮询任务状态
    status_url = f"{url}/{task_id}"
    while True:
        time.sleep(5)
        status_resp = requests.get(status_url, headers=headers)
        if status_resp.status_code != 200:
            print(f"❌ 轮询失败: {status_resp.text}")
            return None, None
        
        data = status_resp.json().get("data", {})
        task_status = data.get("task_status")
        if task_status == "succeed":
            # 任务成功，获取voice_id和preview_url
            voices = data.get("task_result", {}).get("voices", [])
            if voices:
                voice_id = voices[0].get("voice_id")
                preview_url = voices[0].get("trial_url")
                print(f"✅ 音色 '{voice_name}' 创建成功! voice_id: {voice_id}")
                return voice_id, preview_url
            else:
                print(f"❌ 任务成功但未返回音色信息: {data}")
                return None, None
        elif task_status == "failed":
            print(f"❌ 音色 '{voice_name}' 创建失败: {data}")
            return None, None
        print(f"⏳ 任务 {task_id} 状态: {task_status}, 等待中...")

def main():
    created_voices = []
    for voice in NEW_VOICES:
        voice_id, preview_url = create_custom_voice(voice["name"], voice["voice_url"])
        if voice_id:
            created_voices.append({
                "id": voice_id,
                "name": voice["name"],
                "preview_url": preview_url,
                "type": "clone"
            })
        else:
            print(f"⚠️ 音色 '{voice['name']}' 创建失败，请检查音频文件或网络后重试。")
    
    # 将创建成功的音色列表输出为JS文件内容
    if created_voices:
        manual_voices_js = "export const MANUAL_VOICES = " + json.dumps(created_voices, ensure_ascii=False, indent=2) + ";"
        with open("manual_voices.generated.js", "w", encoding="utf-8") as f:
            f.write(manual_voices_js)
        print("\n🎉 批量创建完成！")
        print("=" * 50)
        print(f"成功创建 {len(created_voices)} 个音色，已生成配置文件 'manual_voices.generated.js'。")
        print("请将该文件内容复制到你的前端项目中的 'src/data/manualVoices.js'。")
        print("=" * 50)
    else:
        print("❌ 没有音色创建成功，请检查网络、音频文件或API密钥后重试。")

if __name__ == "__main__":
    main()