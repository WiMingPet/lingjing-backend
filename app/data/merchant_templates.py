"""
电商商品套图 - 预设模板和模特
"""

TEMPLATE_MODELS = {
    "white_bg": {
        "name": "白底主图",
        "prompt_suffix": "白色背景，电商主图风格，产品居中展示，高清细节",
    },
    "scene": {
        "name": "场景展示",
        "prompt_suffix": "简约时尚场景，电商风格，产品自然摆放，光线柔和",
    },
}

# 预设模特图（仅服装类使用）
MODEL_IMAGES = {
    "female": "https://media.lingjing-media.com/%E5%AE%B6%E9%A6%A8.png",  # 家馨
    "male": "https://media.lingjing-media.com/%E4%B8%81%E5%8A%9B.png",  # 丁力
    "male2": "https://media.lingjing-media.com/%E6%96%87%E5%BC%BA.png",  # 文强
}

# 非服装类商品不指定模特，直接生成商品图