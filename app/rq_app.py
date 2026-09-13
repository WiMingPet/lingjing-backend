"""
RQ 配置 - 三个队列
"""
import os
import redis
from rq import Queue

REDIS_URL = os.getenv("REDIS_URL") or os.getenv("REDIS_URI") or "redis://localhost:6379/0"
if not REDIS_URL.rstrip("/").split("/")[-1].isdigit():
    REDIS_URL = REDIS_URL.rstrip("/") + "/0"

print(f"[RQ] 使用 Redis URL: {REDIS_URL[:30]}...")

redis_conn = redis.from_url(REDIS_URL)

# 三个队列，默认超时30分钟
queue_image = Queue("image", connection=redis_conn, default_timeout=1800)
queue_video = Queue("video", connection=redis_conn, default_timeout=1800)
queue_other = Queue("other", connection=redis_conn, default_timeout=1800)

print("[RQ] 队列初始化完成: image / video / other")