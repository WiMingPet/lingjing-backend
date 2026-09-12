"""
RQ 配置
"""
import os
import redis
from rq import Queue

# 读取 Redis URL，优先用 REDIS_URL，其次 REDIS_URI
REDIS_URL = os.getenv("REDIS_URL") or os.getenv("REDIS_URI") or "redis://localhost:6379/0"

# 确保 URL 末尾有 /0
if not REDIS_URL.rstrip("/").split("/")[-1].isdigit():
    REDIS_URL = REDIS_URL.rstrip("/") + "/0"

print(f"[RQ] 使用 Redis URL: {REDIS_URL[:30]}...")

redis_conn = redis.from_url(REDIS_URL)
video_queue = Queue("video", connection=redis_conn)

print("[RQ] RQ 配置完成")