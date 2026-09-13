"""
价格配置 - 统一管理各模块扣费
"""

# ========== 视频生成 ==========
VIDEO_PRICES = {
    '2.6': {
        'off': {5: 25, 10: 50}
    },
    '3.0': {
        'off': {5: 45, 10: 90, 15: 135},
        'native': {5: 60, 10: 120, 15: 180}
    }
}

# ========== 其他模块 ==========
IMAGE_COST = 5
TRYON_COST = 80
DIGITAL_HUMAN_COST = 60
ECOMMERCE_VIDEO_COST = 100
MULTI_ANGLE_COST = 10

# ========== 电商套图 ==========
MERCHANT_WHITE_BG_COST = 10
MERCHANT_SCENE_COST_PER_IMAGE = 10


# ========== 统一查询接口 ==========
def get_video_cost(model: str, sound: str, duration: int) -> int:
    """获取视频生成扣费"""
    return VIDEO_PRICES.get(model, {}).get(sound, {}).get(duration, 0)


def get_merchant_cost(template: str, scene_count: int = 0) -> int:
    """获取电商套图扣费"""
    cost = 0
    if template == "white_bg":
        cost += MERCHANT_WHITE_BG_COST
    if template == "scene":
        cost += scene_count * MERCHANT_SCENE_COST_PER_IMAGE
    return cost