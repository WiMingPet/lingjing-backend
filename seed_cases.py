"""
批量录入 cases 数据
用法：
  本地：py seed_cases.py
  线上：py seed_cases.py https://api.lingjing-media.com
"""
import os
import sys
import json
import requests

# ========== 配置 ==========
if len(sys.argv) > 1:
    API_BASE = sys.argv[1].rstrip('/')
else:
    API_BASE = "http://localhost:8000"

API = f"{API_BASE}/api/cases"
ADMIN_KEY = os.getenv("ADMIN_KEY", "lingjing-admin-2026M1988")

# JSON 文件路径（和脚本同目录）
JSON_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases_data.json")

print(f"[SEED] 目标 API: {API}")
print(f"[SEED] 数据文件: {JSON_FILE}")
print("-" * 60)


def load_cases():
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def to_form_data(item):
    """把 JSON 里的布尔值 / 数字转成字符串（form-data 需要字符串）"""
    data = {}
    for k, v in item.items():
        if isinstance(v, bool):
            data[k] = "true" if v else "false"
        elif v is None:
            data[k] = ""
        else:
            data[k] = str(v)
    return data


def main():
    try:
        cases = load_cases()
    except FileNotFoundError:
        print(f"❌ 找不到 {JSON_FILE}")
        return
    except json.JSONDecodeError as e:
        print(f"❌ JSON 格式错误: {e}")
        return

    print(f"[SEED] 共 {len(cases)} 条数据，开始录入...\n")

    success = 0
    fail = 0

    for i, c in enumerate(cases):
        title = c.get("title", f"未命名-{i+1}")
        try:
            data = to_form_data(c)
            resp = requests.post(
                API,
                data=data,
                headers={"X-Admin-Key": ADMIN_KEY},
                timeout=30,
            )
            if resp.status_code == 200 and resp.json().get("code") == 200:
                print(f"✅ 第 {i+1} 条: {title}")
                success += 1
            else:
                print(f"❌ 第 {i+1} 条失败: {title}")
                print(f"   HTTP {resp.status_code}: {resp.text[:200]}")
                fail += 1
        except Exception as e:
            print(f"❌ 第 {i+1} 条异常: {title} -> {e}")
            fail += 1

    print("-" * 60)
    print(f"[SEED] 完成: 成功 {success}, 失败 {fail}")


if __name__ == "__main__":
    main()