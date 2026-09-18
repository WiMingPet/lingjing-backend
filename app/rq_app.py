"""
RQ 配置 - 三个队列
"""
import os
import redis

# ========== 兼容 Windows 本地测试 ==========
try:
    from rq import Queue
    RQ_AVAILABLE = True
except Exception as e:
    print(f"[RQ] RQ 导入失败（Windows 不支持）: {e}")
    RQ_AVAILABLE = False
    Queue = None
# ==========================================

REDIS_URL = os.getenv("REDIS_URL") or os.getenv("REDIS_URI") or "redis://localhost:6379/0"
if not REDIS_URL.rstrip("/").split("/")[-1].isdigit():
    REDIS_URL = REDIS_URL.rstrip("/") + "/0"

print(f"[RQ] 使用 Redis URL: {REDIS_URL[:30]}...")

if RQ_AVAILABLE:
    redis_conn = redis.from_url(REDIS_URL)
    queue_image = Queue("image", connection=redis_conn, default_timeout=1800)
    queue_video = Queue("video", connection=redis_conn, default_timeout=1800)
    queue_other = Queue("other", connection=redis_conn, default_timeout=1800)
    print("[RQ] 队列初始化完成: image / video / other")
else:
    queue_image = None
    queue_video = None
    queue_other = None
    print("[RQ] 跳过队列初始化（Windows 本地测试）")